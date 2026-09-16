"""The frozen pre-snap feature list must never contain an outcome or post-snap field."""

import pytest

from src import config

# Anything known only after the snap. Extend this list; never shorten it.
POST_SNAP_FIELDS = {
    "ppa", "EPA", "epa", "yards_gained", "explosive", "explosive_alt", "is_giveaway", "turnover", "int",
    "fumble_vec", "completion", "touchdown", "scoring", "ep_after", "wp_after", "wpa", "def_EPA",
    "down_end", "distance_end", "yards_to_goal_end", "TimeSecsRem_end", "pos_score_diff", "score_pts",
    "is_sack", "sack", "family_from_text", "play_type", "play_text", "yds_rushed", "yds_receiving",
    "is_accepted_penalty", "is_no_play", "is_garbage_time", "in_model_sample", "in_team_profile",
}


def test_feature_list_has_no_post_snap_fields():
    assert not set(config.PRE_SNAP_FEATURES) & POST_SNAP_FIELDS


@pytest.mark.parametrize("feature", config.PRE_SNAP_FEATURES)
def test_feature_names_do_not_look_post_snap(feature):
    assert not feature.endswith(("_end", "_after")), feature
