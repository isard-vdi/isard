"""TDD for the #2084 stopgap ① pure helpers (streams/trim.py).

Durability core: consumer-driven MINID trim floor + progress-split routing.
No redis, no heavy imports — pure functions only.
"""

from isardvdi_change_handler.streams.trim import (
    PROGRESS_STREAM,
    RESULT_STREAM,
    compute_trim_floor,
    min_stream_id,
    stream_for_kind,
)

# --- min_stream_id: redis stream IDs compare as (ms:int, seq:int), not lexically ---


def test_min_stream_id_compares_ms_numerically_not_lexically():
    # "9-0" < "100-0" numerically, but "100-0" < "9-0" lexically -> must pick 9-0
    assert min_stream_id("100-0", "9-0") == "9-0"


def test_min_stream_id_breaks_ties_on_sequence():
    assert min_stream_id("1500-5", "1500-3") == "1500-3"


# --- compute_trim_floor: never trim past the read frontier nor below oldest un-ACKed ---


def test_floor_is_none_when_nothing_delivered_yet():
    assert compute_trim_floor(None, None) is None


def test_floor_is_none_for_zero_last_delivered_and_no_pending():
    # "0-0" means the group has delivered nothing -> trimming would be meaningless/unsafe
    assert compute_trim_floor("0-0", None) is None


def test_floor_is_last_delivered_when_pel_is_empty():
    # No pending entries -> everything up to last-delivered is ACKed -> safe to trim to it
    assert compute_trim_floor("1500-0", None) == "1500-0"


def test_floor_keeps_oldest_unacked_pending_entry():
    # A delivered-but-un-ACKed entry at 1400-0 must survive trimming even though
    # the group has delivered up to 1500-5.
    assert compute_trim_floor("1500-5", "1400-0") == "1400-0"


def test_floor_never_exceeds_pending_even_on_same_ms():
    assert compute_trim_floor("1500-5", "1500-3") == "1500-3"


# --- stream_for_kind: progress split off the result stream ---


def test_progress_routes_to_its_own_stream():
    assert stream_for_kind("progress") == PROGRESS_STREAM
    assert PROGRESS_STREAM == "stream:progress"


def test_result_stays_on_task_results_stream():
    assert stream_for_kind("result") == RESULT_STREAM
    assert RESULT_STREAM == "stream:task-results"
