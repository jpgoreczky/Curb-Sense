from datetime import timedelta

import pytest

from services.ingestion import EngineSettings, _quorum_winner

SETTINGS = EngineSettings(
    point_match_radius_m=15,
    segment_snap_radius_m=20,
    conflict_decay_window=timedelta(hours=48),
    quorum_min_votes=3,
    quorum_margin=0.75,
)


@pytest.mark.parametrize(
    ("tier1", "tier2", "expected"),
    [
        (0, 0, None),  # no decided votes
        (0, 2, None),  # unanimous but under min votes
        (0, 3, "tier2"),  # min votes, 100%
        (3, 1, "tier1"),  # exactly 75%
        (3, 2, None),  # 60% < margin
        (3, 3, None),  # tie
        (1, 6, "tier2"),  # ~86%
    ],
)
def test_quorum_winner(tier1, tier2, expected):
    assert _quorum_winner(tier1, tier2, SETTINGS) == expected
