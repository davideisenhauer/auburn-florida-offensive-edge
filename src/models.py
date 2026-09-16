"""League baseline models: tune on 2021-2024, test once on 2025, refit, and score every play.

Run from the project root (after src.clean):
    .venv/bin/python -m src.models

Writes:
    outputs/tables/model_tuning.csv            leave-one-season-out tuning within 2021-2024
    outputs/tables/model_test_2025.csv         the one-time 2025 test for every candidate and the naive baseline
    outputs/tables/model_test_groups_2025.csv  mean error by situation group
    outputs/tables/calibration_2025.csv        explosive calibration by probability decile
    outputs/tables/environment_check_2026.csv  the 2026 environment check (spec section 7.3)
    outputs/models/model_selection.json        chosen specifications, gate metrics, environment corrections
    outputs/models/*.joblib                    final and sensitivity models
    data/interim/predictions.parquet           predictions for every scorable play

Definitions are in docs/analysis_spec.md sections 7 and 7.5.
"""

import json
from dataclasses import asdict, dataclass, field

import joblib
import numpy as np
import pandas as pd
import xgboost as xgb
from scipy.optimize import brentq
from scipy.special import expit, logit
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score
from sklearn.pipeline import make_pipeline

from src import config
from src.features import boosted_matrix, linear_preprocessor, model_frame

TARGETS = {
    "value": ("ppa", "regression"),
    "explosive": ("explosive", "classification"),
    "explosive_alt": ("explosive_alt", "classification"),
}
PRIMARY_TARGETS = ["value", "explosive"]
RIDGE_ALPHAS = [1.0, 10.0, 100.0, 1000.0, 10000.0]
LOGISTIC_CS = [0.01, 0.1, 1.0]
XGB_GRID = [(4, "light"), (6, "light"), (4, "heavy"), (6, "heavy")]
MIN_CHILD_WEIGHT = {"regression": {"light": 500, "heavy": 2000}, "classification": {"light": 30, "heavy": 120}}
XGB_LEARNING_RATE, XGB_MAX_ROUNDS, XGB_EARLY_STOP = 0.1, 3000, 100
SELECTION_MIN_RELATIVE_GAIN = 0.01  # boosted must cut MAE (value) or Brier (explosive) by 1%
BIAS_REDUCTION_REQUIRED = 0.50
MIN_ROC_AUC = 0.55
CALIBRATION_RATIO = (0.95, 1.05)
CALIBRATION_SLOPE = (0.85, 1.15)
GROUP_KEYS = ["down_bin", "distance_bin", "field_bin", "play_family"]
BOOTSTRAP_REPS = 2000
SEED = 20260917
MODELS_DIR = config.OUTPUTS_DIR / "models"


def log(message: str) -> None:
    print(message, flush=True)


# ---------------------------------------------------------------- model wrapper

@dataclass
class Spec:
    family: str  # "linear" or "boosted"
    kind: str  # "regression" or "classification"
    use_spread: bool = True
    params: dict = field(default_factory=dict)


class BaselineModel:
    def __init__(self, spec: Spec):
        self.spec = spec

    def fit(self, X: pd.DataFrame, y: np.ndarray, eval_set=None):
        s = self.spec
        X = X if s.use_spread else X.drop(columns=["offense_spread", "spread_missing"])
        if s.family == "linear":
            estimator = Ridge(alpha=s.params["penalty"]) if s.kind == "regression" else LogisticRegression(C=s.params["penalty"], max_iter=3000)
            self.model_ = make_pipeline(linear_preprocessor(s.use_spread), estimator).fit(X, y)
            return self
        common = dict(
            tree_method="hist", learning_rate=XGB_LEARNING_RATE, max_depth=s.params["max_depth"],
            min_child_weight=s.params["min_child_weight"], subsample=0.8, reg_lambda=1.0,
            n_estimators=s.params.get("n_estimators", XGB_MAX_ROUNDS), n_jobs=-1, random_state=SEED,
        )
        if eval_set is not None:
            common["early_stopping_rounds"] = XGB_EARLY_STOP
        if s.kind == "regression":
            self.model_ = xgb.XGBRegressor(objective="reg:squarederror", eval_metric="rmse", **common)
        else:
            self.model_ = xgb.XGBClassifier(objective="binary:logistic", eval_metric="logloss", **common)
        fit_kwargs = {"verbose": False}
        if eval_set is not None:
            Xv, yv = eval_set
            Xv = Xv if s.use_spread else Xv.drop(columns=["offense_spread", "spread_missing"])
            fit_kwargs["eval_set"] = [(boosted_matrix(Xv), yv)]
        self.model_.fit(boosted_matrix(X), y, **fit_kwargs)
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        s = self.spec
        X = X if s.use_spread else X.drop(columns=["offense_spread", "spread_missing"])
        inputs = X if s.family == "linear" else boosted_matrix(X)
        if s.kind == "regression":
            return self.model_.predict(inputs)
        return self.model_.predict_proba(inputs)[:, 1]


# ---------------------------------------------------------------- metrics

def loss(kind: str, y, pred) -> float:
    return float(np.mean((y - pred) ** 2)) if kind == "regression" else float(log_loss(y, np.clip(pred, 1e-6, 1 - 1e-6)))


def calibration_fit(y, p) -> tuple[float, float]:
    """Intercept and slope of a logistic regression of y on logit(p), by Newton-Raphson."""
    x = logit(np.clip(p, 1e-6, 1 - 1e-6))
    X = np.column_stack([np.ones_like(x), x])
    beta = np.array([0.0, 1.0])
    for _ in range(50):
        mu = expit(X @ beta)
        w = mu * (1 - mu)
        step = np.linalg.solve(X.T @ (X * w[:, None]), X.T @ (y - mu))
        beta += step
        if np.abs(step).max() < 1e-10:
            break
    return float(beta[0]), float(beta[1])


def group_bias(frame: pd.DataFrame, y, pred) -> float:
    """Play-weighted mean absolute bias across down x distance x field position x play family groups."""
    g = frame[GROUP_KEYS].assign(err=np.asarray(y, float) - pred).groupby(GROUP_KEYS, observed=True).err.agg(["mean", "size"])
    return float(np.average(g["mean"].abs(), weights=g["size"]))


def metrics(kind: str, frame: pd.DataFrame, y, pred) -> dict:
    y = np.asarray(y, float)
    out = {"plays": len(y), "mean_error": float(np.mean(y - pred)), "group_bias": group_bias(frame, y, pred)}
    if kind == "regression":
        out |= {"mae": float(np.mean(np.abs(y - pred))), "rmse": float(np.sqrt(np.mean((y - pred) ** 2))),
                "r2": float(1 - np.sum((y - pred) ** 2) / np.sum((y - y.mean()) ** 2))}
    else:
        p = np.clip(pred, 1e-6, 1 - 1e-6)
        constant = np.unique(np.round(p, 12)).size == 1
        intercept, slope = (np.nan, np.nan) if constant else calibration_fit(y, p)
        out |= {"brier": float(brier_score_loss(y, p)), "log_loss": float(log_loss(y, p)),
                "roc_auc": np.nan if constant else float(roc_auc_score(y, p)),
                "average_precision": float(average_precision_score(y, p)),
                "observed_over_expected": float(y.sum() / p.sum()),
                "calibration_intercept": np.nan if constant else intercept, "calibration_slope": np.nan if constant else slope}
    return out


def cluster_ratio_interval(games, numerator, denominator, level=0.95) -> tuple[float, float]:
    """Game-clustered bootstrap interval for sum(numerator) / sum(denominator)."""
    g = pd.DataFrame({"g": games, "num": numerator, "den": denominator}).groupby("g").sum()
    idx = np.random.default_rng(SEED).integers(0, len(g), size=(BOOTSTRAP_REPS, len(g)))
    ratios = g.num.to_numpy()[idx].sum(axis=1) / g.den.to_numpy()[idx].sum(axis=1)
    alpha = (1 - level) / 2
    lo, hi = np.quantile(ratios, [alpha, 1 - alpha])
    return float(lo), float(hi)


# ---------------------------------------------------------------- tuning

def tune(family: str, kind: str, X: pd.DataFrame, y: np.ndarray, seasons: np.ndarray, target: str) -> tuple[Spec, list[dict]]:
    rows = []
    if family == "linear":
        grid = RIDGE_ALPHAS if kind == "regression" else LOGISTIC_CS
        for penalty in grid:
            fold_losses = []
            for season in config.TRAIN_SEASONS:
                tr, va = seasons != season, seasons == season
                model = BaselineModel(Spec("linear", kind, True, {"penalty": penalty})).fit(X[tr], y[tr])
                fold_losses.append(loss(kind, y[va], model.predict(X[va])))
            rows.append({"target": target, "family": family, "setting": f"penalty={penalty:g}",
                         "cv_loss": float(np.mean(fold_losses)), "params": {"penalty": penalty}})
            log(f"    {target} linear penalty={penalty:g}: cv loss {rows[-1]['cv_loss']:.6f}")
    else:
        for depth, leaf in XGB_GRID:
            params = {"max_depth": depth, "min_child_weight": MIN_CHILD_WEIGHT[kind][leaf]}
            fold_losses, iterations = [], []
            for season in config.TRAIN_SEASONS:
                tr, va = seasons != season, seasons == season
                model = BaselineModel(Spec("boosted", kind, True, params)).fit(X[tr], y[tr], eval_set=(X[va], y[va]))
                iterations.append(model.model_.best_iteration + 1)
                fold_losses.append(loss(kind, y[va], model.predict(X[va])))
            params = params | {"n_estimators": int(round(np.mean(iterations)))}
            rows.append({"target": target, "family": family, "setting": f"depth={depth}, leaf={leaf}",
                         "cv_loss": float(np.mean(fold_losses)), "params": params})
            log(f"    {target} boosted depth={depth} leaf={leaf}: cv loss {rows[-1]['cv_loss']:.6f}, trees {params['n_estimators']}")
    best = min(rows, key=lambda r: r["cv_loss"])
    return Spec(family, kind, True, best["params"]), rows


# ---------------------------------------------------------------- 2026 environment check

def environment_check(frame: pd.DataFrame, target: str, pred: np.ndarray, label: str) -> dict:
    column, kind = TARGETS[target]
    y = frame[column].astype(float).to_numpy()
    games = frame.game_id.to_numpy()
    row = {"model": label, "target": target, "plays": len(y), "games": int(pd.unique(games).size)}
    if kind == "regression":
        residual = y - pred
        lo, hi = cluster_ratio_interval(games, residual, np.ones_like(residual))
        mean = float(residual.mean())
        triggered = abs(mean) > config.RECALIBRATE_PPA_MEAN_RESIDUAL and (lo > 0 or hi < 0)
        row |= {"statistic": "mean residual", "estimate": mean, "ci_low": lo, "ci_high": hi, "triggered": triggered,
                "correction": mean if triggered else 0.0, "correction_type": "additive constant"}
    else:
        lo, hi = cluster_ratio_interval(games, y, pred)
        ratio = float(y.sum() / pred.sum())
        low_bound, high_bound = config.RECALIBRATE_EXPLOSIVE_RATIO
        triggered = (ratio < low_bound or ratio > high_bound) and (lo > 1 or hi < 1)
        offset = 0.0
        if triggered:
            z = logit(np.clip(pred, 1e-6, 1 - 1e-6))
            offset = brentq(lambda d: expit(z + d).sum() - y.sum(), -5, 5)
        row |= {"statistic": "observed / expected", "estimate": ratio, "ci_low": lo, "ci_high": hi, "triggered": triggered,
                "correction": float(offset), "correction_type": "logit offset"}
    return row


def apply_correction(target: str, pred: np.ndarray, correction: float) -> np.ndarray:
    if correction == 0:
        return pred
    if TARGETS[target][1] == "regression":
        return pred + correction
    return expit(logit(np.clip(pred, 1e-6, 1 - 1e-6)) + correction)


# ---------------------------------------------------------------- pipeline

def main() -> None:
    plays = pd.read_parquet(config.PROCESSED_DIR / "plays.parquet")
    sample = plays[plays.in_model_sample].reset_index(drop=True)
    X = model_frame(sample)
    seasons = sample.season.to_numpy()
    selection, tuning_rows, test_rows, group_rows, calibration_rows = {}, [], [], [], []
    train = np.isin(seasons, config.TRAIN_SEASONS)
    test = seasons == config.TEST_SEASON
    test_predictions, boosted_specs = {}, {}

    for target in PRIMARY_TARGETS:
        column, kind = TARGETS[target]
        y = sample[column].astype(float).to_numpy()
        log(f"Tuning {target} on 2021-2024 (leave one season out)")
        specs = {}
        for family in ("linear", "boosted"):
            specs[family], rows = tune(family, kind, X[train], y[train], seasons[train], target)
            tuning_rows += rows
        boosted_specs[target] = specs["boosted"]

        log(f"Testing {target} once on 2025")
        preds = {"naive": np.full(test.sum(), y[train].mean())}
        for family in ("linear", "boosted"):
            for use_spread in (True, False):
                spec = Spec(family, kind, use_spread, specs[family].params)
                name = family + ("" if use_spread else " (no spread)")
                preds[name] = BaselineModel(spec).fit(X[train], y[train]).predict(X[test])
        frame = sample[test]
        for name, pred in preds.items():
            test_rows.append({"target": target, "candidate": name} | metrics(kind, frame, y[test], pred))

        key = "mae" if kind == "regression" else "brier"
        err = (lambda p: np.abs(y[test] - p)) if kind == "regression" else (lambda p: (y[test] - p) ** 2)
        linear_err, boosted_err = err(preds["linear"]), err(preds["boosted"])
        gain = 1 - boosted_err.sum() / linear_err.sum()
        ratio_lo, ratio_hi = cluster_ratio_interval(frame.game_id, boosted_err, linear_err)
        chosen = "boosted" if gain >= SELECTION_MIN_RELATIVE_GAIN else "linear"
        spec = specs[chosen]

        chosen_metrics = next(r for r in test_rows if r["target"] == target and r["candidate"] == chosen)
        naive_metrics = next(r for r in test_rows if r["target"] == target and r["candidate"] == "naive")
        bias_reduction = 1 - chosen_metrics["group_bias"] / naive_metrics["group_bias"]
        if kind == "regression":
            primary_better = chosen_metrics["rmse"] < naive_metrics["rmse"]
            all_conditions = primary_better and chosen_metrics["mae"] < naive_metrics["mae"] and bias_reduction >= BIAS_REDUCTION_REQUIRED
        else:
            primary_better = chosen_metrics["brier"] < naive_metrics["brier"]
            all_conditions = (primary_better and chosen_metrics["log_loss"] < naive_metrics["log_loss"]
                              and chosen_metrics["roc_auc"] >= MIN_ROC_AUC and bias_reduction >= BIAS_REDUCTION_REQUIRED)
        selection[target] = {
            "chosen": chosen, "spec": asdict(spec),
            "boosted_relative_gain": {"metric": key, "estimate": gain, "ci95": [1 - ratio_hi, 1 - ratio_lo]},
            "beats_naive": bool(all_conditions), "only_marginal": bool(primary_better and not all_conditions),
            "group_bias_reduction": bias_reduction,
        }
        if kind == "classification":
            lo, hi = CALIBRATION_RATIO
            s_lo, s_hi = CALIBRATION_SLOPE
            selection[target]["calibrated"] = bool(lo <= chosen_metrics["observed_over_expected"] <= hi
                                                   and s_lo <= chosen_metrics["calibration_slope"] <= s_hi)
            deciles = pd.qcut(preds[chosen], 10, labels=False, duplicates="drop")
            cal = pd.DataFrame({"decile": deciles + 1, "predicted": preds[chosen], "observed": y[test]}).groupby("decile").agg(
                plays=("observed", "size"), mean_predicted=("predicted", "mean"), observed_rate=("observed", "mean")).reset_index()
            calibration_rows.append(cal.assign(target=target, candidate=chosen))
        log(f"  {target}: boosted {key} gain {gain:+.2%} -> chosen {chosen}; beats naive: {all_conditions}")

        for name in ("naive", chosen):
            week_label = np.where(frame.game_season_type.eq("postseason"), "postseason", frame.week.map("{:02d}".format))
            errors = frame.assign(error=y[test] - preds[name], week=week_label)  # bowls are also numbered week 1
            for key_col in GROUP_KEYS + ["week"]:
                g = errors.groupby(key_col, observed=True).agg(plays=("error", "size"), mean_error=("error", "mean")).reset_index()
                group_rows.append(g.rename(columns={key_col: "group"}).assign(target=target, candidate=name, dimension=key_col))
        test_predictions[target] = preds[chosen]

    # Alternate explosive target: same family as the primary explosive model, tuned the same way
    column, kind = TARGETS["explosive_alt"]
    y_alt = sample[column].astype(float).to_numpy()
    log("Tuning explosive_alt with the chosen explosive family")
    alt_spec, rows = tune(selection["explosive"]["chosen"], kind, X[train], y_alt[train], seasons[train], "explosive_alt")
    tuning_rows += rows
    selection["explosive_alt"] = {"chosen": alt_spec.family, "spec": asdict(alt_spec)}
    specs_final = {t: Spec(**selection[t]["spec"]) for t in TARGETS}

    # Final (2021-2025) and sensitivity (2023-2025) refits
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    historical = np.isin(seasons, config.HISTORICAL_SEASONS)
    sensitivity = np.isin(seasons, config.SENSITIVITY_SEASONS)
    fitted = {}
    for target, spec in specs_final.items():
        y = sample[TARGETS[target][0]].astype(float).to_numpy()
        for label, mask in (("final", historical), ("sensitivity", sensitivity)):
            log(f"Refitting {target} {label}")
            fitted[(target, label)] = BaselineModel(spec).fit(X[mask], y[mask])
            joblib.dump(fitted[(target, label)], MODELS_DIR / f"{target}_{label}.joblib")
    # Boosted candidates refit on 2021-2025 for robustness check 10 only
    for target in PRIMARY_TARGETS:
        y = sample[TARGETS[target][0]].astype(float).to_numpy()
        log(f"Refitting {target} boosted_final (robustness check 10)")
        fitted[(target, "boosted_final")] = BaselineModel(boosted_specs[target]).fit(X[historical], y[historical])
    selection["boosted_check_specs"] = {t: asdict(s) for t, s in boosted_specs.items()}

    # Leave-one-season-out predictions for 2021-2025 (inputs to the shrinkage reliability test)
    predictions = sample.loc[historical, ["play_key"]].copy()
    for target, spec in specs_final.items():
        y = sample[TARGETS[target][0]].astype(float).to_numpy()
        out = np.full(len(sample), np.nan)
        for season in config.HISTORICAL_SEASONS:
            log(f"Cross-fitting {target}, holding out {season}")
            fit_mask = historical & (seasons != season)
            out[seasons == season] = BaselineModel(spec).fit(X[fit_mask], y[fit_mask]).predict(X[seasons == season])
        predictions[f"{target}_crossfit"] = out[historical]
    test_keys = sample.loc[test, "play_key"].to_numpy()
    for target, pred in test_predictions.items():
        predictions[f"{target}_test"] = pd.Series(pred, index=test_keys).reindex(predictions.play_key).to_numpy()

    # Score every scorable 2026 snap, including ones outside the model sample (for robustness check 3)
    current = plays[(plays.season == config.CURRENT_SEASON) & plays.valid_state & ~plays.is_overtime
                    & ~plays.is_no_play & ~plays.is_offsetting].reset_index(drop=True)
    Xc = model_frame(current)
    scored = current[["play_key"]].copy()
    for (target, label), model in fitted.items():
        scored[f"{target}_{label}"] = model.predict(Xc)

    # 2026 environment check on every other 2026 FBS model-sample play
    matchup_games = set(current.loc[(current.pos_team == config.OFFENSE_TEAM) | (current.def_pos_team == config.DEFENSE_TEAM), "game_id"])
    env_mask = current.in_model_sample & ~current.game_id.isin(matchup_games)
    env_frame = current[env_mask]
    env_rows, corrections = [], {}
    for label in ("final", "sensitivity", "boosted_final"):
        corrections[label] = {}
        for target in (TARGETS if label != "boosted_final" else PRIMARY_TARGETS):
            row = environment_check(env_frame, target, scored.loc[env_mask, f"{target}_{label}"].to_numpy(), label)
            env_rows.append(row)
            corrections[label][target] = row["correction"]
            scored[f"{target}_{label}_adj"] = apply_correction(target, scored[f"{target}_{label}"].to_numpy(), row["correction"])
    early_2025 = sample[test & np.isin(sample.week, config.CURRENT_WEEKS) & sample.game_season_type.eq("regular").to_numpy()]
    early_keys = early_2025.play_key.to_numpy()
    for target in PRIMARY_TARGETS:
        pred = pd.Series(test_predictions[target], index=test_keys).reindex(early_keys).to_numpy()
        row = environment_check(early_2025, target, pred, "2025 Weeks 1-2 benchmark (2021-2024 model)")
        env_rows.append(row | {"triggered": None, "correction": None})
    selection["environment_corrections"] = corrections

    all_predictions = pd.concat([predictions, scored], ignore_index=True)
    config.INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    all_predictions.to_parquet(config.INTERIM_DIR / "predictions.parquet", index=False)

    config.TABLES_DIR.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(tuning_rows).assign(params=lambda d: d.params.map(json.dumps)).to_csv(config.TABLES_DIR / "model_tuning.csv", index=False)
    pd.DataFrame(test_rows).to_csv(config.TABLES_DIR / "model_test_2025.csv", index=False)
    pd.concat(group_rows).to_csv(config.TABLES_DIR / "model_test_groups_2025.csv", index=False)
    pd.concat(calibration_rows).to_csv(config.TABLES_DIR / "calibration_2025.csv", index=False)
    pd.DataFrame(env_rows).to_csv(config.TABLES_DIR / "environment_check_2026.csv", index=False)
    (MODELS_DIR / "model_selection.json").write_text(json.dumps(selection, indent=2, default=float))
    log("Done.")


if __name__ == "__main__":
    from src import models  # run via the importable module so saved models unpickle from anywhere

    models.main()
