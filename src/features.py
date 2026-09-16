"""Model inputs built only from the frozen pre-snap features (docs/analysis_spec.md sections 7.1 and 7.5).

`model_frame` is the single entry point from the play table to any model, so nothing outside
config.PRE_SNAP_FEATURES can reach a predictor.
"""

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, SplineTransformer, StandardScaler

from src import config

SCORE_CLIP = 42
SPREAD_CLIP = 50
VENUE_CODE = {"home": 1.0, "neutral": 0.0, "away": -1.0}
SPREAD_FEATURES = ["offense_spread", "spread_missing"]


def model_frame(plays: pd.DataFrame, use_spread: bool = True) -> pd.DataFrame:
    """Pre-snap feature columns with clipping applied. Raises if any feature is missing unexpectedly."""
    X = plays[config.PRE_SNAP_FEATURES].copy()
    for flag in ("is_pass", "goal_to_go", "spread_missing"):
        X[flag] = X[flag].astype(float)
    X["score_diff"] = X.score_diff.clip(-SCORE_CLIP, SCORE_CLIP)
    X["offense_spread"] = X.offense_spread.astype(float).clip(-SPREAD_CLIP, SPREAD_CLIP)
    required = X.drop(columns=["offense_spread"])
    if required.isna().any().any():
        raise ValueError(f"missing pre-snap values in {required.columns[required.isna().any()].tolist()}")
    if not use_spread:
        X = X.drop(columns=SPREAD_FEATURES)
    return X


class DownDistance(BaseEstimator, TransformerMixin):
    """Indicators for 2nd, 3rd, and 4th down plus a separate log-distance slope for each down."""

    def fit(self, X, y=None):
        return self

    def transform(self, X):
        down, log_distance = X["down"].to_numpy(), X["log_distance"].to_numpy()
        columns = [(down == d).astype(float) for d in (2, 3, 4)]
        columns += [(down == d) * log_distance for d in (1, 2, 3, 4)]
        return np.column_stack(columns)

    def get_feature_names_out(self, input_features=None):
        return np.array([f"down_{d}" for d in (2, 3, 4)] + [f"log_distance_down_{d}" for d in (1, 2, 3, 4)])


class FamilyFieldPosition(BaseEstimator, TransformerMixin):
    """Spline in yards to goal, a second spline for passes only, and the pass indicator."""

    def __init__(self, n_knots: int = 6):
        self.n_knots = n_knots

    def fit(self, X, y=None):
        self.spline_ = SplineTransformer(n_knots=self.n_knots, degree=3, include_bias=False).fit(X[["yards_to_goal"]])
        return self

    def transform(self, X):
        basis = self.spline_.transform(X[["yards_to_goal"]])
        is_pass = X["is_pass"].to_numpy()[:, None]
        return np.hstack([basis, basis * is_pass, is_pass])

    def get_feature_names_out(self, input_features=None):
        k = self.spline_.n_features_out_
        return np.array([f"field_{i}" for i in range(k)] + [f"pass_field_{i}" for i in range(k)] + ["is_pass"])


def spline(n_knots: int = 5):
    return SplineTransformer(n_knots=n_knots, degree=3, include_bias=False)


def linear_preprocessor(use_spread: bool = True):
    parts = [
        ("down_distance", DownDistance(), ["down", "log_distance"]),
        ("family_field", FamilyFieldPosition(), ["yards_to_goal", "is_pass"]),
        ("quarter", OneHotEncoder(categories=[[1, 2, 3, 4]], drop="first", handle_unknown="ignore", sparse_output=False), ["period"]),
        ("clock", spline(), ["half_seconds_remaining"]),
        ("score", spline(), ["score_diff"]),
        ("venue", OneHotEncoder(categories=[["home", "neutral", "away"]], drop="first", sparse_output=False), ["venue"]),
        ("goal_to_go", "passthrough", ["goal_to_go"]),
    ]
    if use_spread:
        parts += [
            ("spread", make_pipeline(SimpleImputer(strategy="constant", fill_value=0.0), spline()), ["offense_spread"]),
            ("spread_missing", "passthrough", ["spread_missing"]),
        ]
    return make_pipeline(ColumnTransformer(parts, verbose_feature_names_out=False), StandardScaler())


def boosted_matrix(X: pd.DataFrame) -> pd.DataFrame:
    """Numeric matrix for XGBoost. Venue becomes home=1, neutral=0, away=-1; a missing spread stays missing."""
    M = X.drop(columns=["log_distance"]).copy()
    M["venue"] = M.venue.map(VENUE_CODE)
    return M.astype(float)
