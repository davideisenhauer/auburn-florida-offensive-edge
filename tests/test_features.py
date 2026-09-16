"""Model inputs: only pre-snap features reach a model, and the baseline design behaves as specified."""

import numpy as np
import pandas as pd
import pytest

from src import config
from src.features import SCORE_CLIP, SPREAD_CLIP, boosted_matrix, linear_preprocessor, model_frame
from src.models import BaselineModel, Spec, apply_correction, calibration_fit, environment_check


def plays(n: int = 400, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    down = rng.integers(1, 5, n).astype(float)
    distance = rng.integers(1, 16, n).astype(float)
    df = pd.DataFrame({
        "is_pass": rng.random(n) < 0.5, "down": down, "distance": distance, "log_distance": np.log(distance),
        "yards_to_goal": rng.integers(16, 99, n).astype(float), "period": rng.integers(1, 5, n),
        "half_seconds_remaining": rng.uniform(0, 1800, n), "score_diff": rng.integers(-60, 60, n).astype(float),
        "venue": rng.choice(["home", "away", "neutral"], n), "goal_to_go": np.zeros(n, bool),
        "offense_spread": rng.uniform(-70, 70, n), "spread_missing": np.zeros(n, bool),
        "ppa": rng.normal(0, 1, n), "explosive": rng.random(n) < 0.07, "yards_gained": rng.integers(-5, 40, n),
        "game_id": rng.integers(0, 40, n),
    })
    df.loc[:9, "offense_spread"] = np.nan
    df.loc[:9, "spread_missing"] = True
    return df


def test_model_frame_uses_only_pre_snap_features():
    X = model_frame(plays())
    assert list(X.columns) == config.PRE_SNAP_FEATURES
    assert "ppa" not in X and "explosive" not in X and "yards_gained" not in X


def test_outcomes_cannot_change_model_inputs():
    df = plays()
    shuffled = df.assign(ppa=df.ppa.sample(frac=1, random_state=1).to_numpy(), yards_gained=0, explosive=True)
    pd.testing.assert_frame_equal(model_frame(df), model_frame(shuffled))


def test_clipping_and_missing_spread():
    X = model_frame(plays())
    assert X.score_diff.abs().max() <= SCORE_CLIP
    assert X.offense_spread.abs().max() <= SPREAD_CLIP
    assert X.offense_spread.isna().sum() == 10
    assert "offense_spread" not in model_frame(plays(), use_spread=False)


def test_missing_required_feature_raises():
    df = plays()
    df.loc[0, "down"] = np.nan
    with pytest.raises(ValueError):
        model_frame(df)


def test_linear_design_is_finite_and_has_family_by_field_terms():
    X = model_frame(plays())
    pre = linear_preprocessor().fit(X)
    design = pre.transform(X)
    names = pre[0].get_feature_names_out()
    assert np.isfinite(design).all()
    assert any(n.startswith("pass_field_") for n in names) and any(n.startswith("log_distance_down_") for n in names)


def test_boosted_matrix_encodes_venue_and_keeps_missing_spread():
    M = boosted_matrix(model_frame(plays()))
    assert set(M.venue.unique()) <= {-1.0, 0.0, 1.0}
    assert M.offense_spread.isna().sum() == 10
    assert "log_distance" not in M


@pytest.mark.parametrize("family", ["linear", "boosted"])
@pytest.mark.parametrize("kind, column", [("regression", "ppa"), ("classification", "explosive")])
def test_models_fit_and_predict(family, kind, column):
    df = plays(2000)
    X, y = model_frame(df), df[column].astype(float).to_numpy()
    params = {"penalty": 1.0} if family == "linear" else {"max_depth": 2, "min_child_weight": 1, "n_estimators": 5}
    pred = BaselineModel(Spec(family, kind, True, params)).fit(X, y).predict(X)
    assert pred.shape == (len(df),) and np.isfinite(pred).all()
    if kind == "classification":
        assert ((pred > 0) & (pred < 1)).all()


def test_calibration_fit_recovers_known_slope():
    rng = np.random.default_rng(3)
    z = rng.normal(-2.5, 1, 200_000)
    y = rng.random(z.size) < 1 / (1 + np.exp(-(0.2 + 0.8 * z)))
    intercept, slope = calibration_fit(y.astype(float), 1 / (1 + np.exp(-z)))
    assert abs(slope - 0.8) < 0.03 and abs(intercept - 0.2) < 0.05


def test_environment_correction_matches_observed_rate():
    rng = np.random.default_rng(4)
    frame = pd.DataFrame({"game_id": rng.integers(0, 300, 60_000), "explosive": rng.random(60_000) < 0.05})
    pred = np.full(len(frame), 0.08)  # model expects 8%, reality is 5%
    row = environment_check(frame, "explosive", pred, "test")
    assert row["triggered"]
    assert abs(apply_correction("explosive", pred, row["correction"]).sum() - frame.explosive.sum()) < 1


def test_environment_check_ignores_small_value_shift():
    rng = np.random.default_rng(5)
    frame = pd.DataFrame({"game_id": rng.integers(0, 300, 60_000), "ppa": rng.normal(0.01, 1.5, 60_000)})
    row = environment_check(frame, "value", np.zeros(len(frame)), "test")
    assert not row["triggered"] and row["correction"] == 0.0
