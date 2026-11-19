# SPDX-License-Identifier: AGPL-3.0-or-later

"""The streamed desktop consolidation matches the grouped one in bounded memory."""

import copy
import tracemalloc
from datetime import datetime, timedelta, timezone

import pytest

T0 = datetime(2026, 1, 5, tzinfo=timezone.utc)
TEMPLATES = ["tmpl-a", "tmpl-b", "tmpl-c"]
CONSUMERS = ("user", "group", "category", "desktop", "deployment", "template")
FORMULA = [{"id": "DHN", "formula": "0.2 * dsk_vcpus / 4 + 0.8 * dsk_mem / 6"}]


def _log_rows(n=300, desktops=40):
    rows = []
    for i in range(n):
        user = i % 15
        row = {
            "id": "log-%d" % i,
            "events": [{"event": "start"}] * 3,
            "desktop_id": "desk-%d" % (i % desktops),
            "desktop_name": "Desktop %d" % (i % desktops),
            "desktop_template_hierarchy": ["base", TEMPLATES[i % 3]],
            "owner_user_id": "user-%d" % user,
            "owner_user_name": "User %d" % user,
            "owner_group_id": "group-%d" % (user % 4),
            "owner_group_name": "Group %d" % (user % 4),
            "owner_category_id": "cat-%d" % (user % 2),
            "owner_category_name": "Category %d" % (user % 2),
            "owner_role_id": "user",
            "hardware_vcpus": 1 + i % 4,
            "hardware_memory": 2097152 * (1 + i % 3),
            "hyp_started": "hyp-%d" % (i % 3),
            "starting_time": T0 + timedelta(minutes=i),
            "started_time": T0 + timedelta(minutes=i, seconds=20),
            "stopped_time": T0 + timedelta(minutes=i + 37 * (1 + i % 7)),
            "starting_by": "desktop-owner",
            "starting_user": "user-%d" % user,
            "stopped_by": "isard-engine",
            "stopped_status": "Stopped",
            "request_ip": "10.0.0.%d" % (i % 250),
            "request_agent_browser": "Firefox",
            "request_agent_platform": "Linux",
            "request_agent_version": "131",
        }
        if i % 3 == 0:
            row["tag"] = "dep-%d" % (i % 5)
            row["deployment_id"] = row["tag"]
            row["deployment_name"] = "Deployment %d" % (i % 5)
        if i % 10 == 0:
            row["hardware_bookables_vgpus"] = ["NVIDIA-A10-4Q"]
        rows.append(row)
    return rows


def _fetch(rows, fields):
    """What the logs query yields, with or without the field projection."""
    for row in rows:
        if fields is None:
            row = {k: v for k, v in row.items() if k != "events"}
        else:
            row = {k: v for k, v in row.items() if k in fields}
        hierarchy = row.get("desktop_template_hierarchy") or []
        row["template_id"] = hierarchy[-1] if hierarchy else None
        row["deployment_id"] = row.get("tag")
        yield row


def _previous(abs_only):
    previous = {}
    for i in range(40):
        for consumer, item in (("desktop", "desk-%d" % i), ("user", "user-%d" % i)):
            row = {
                "pk": "prev-%s-%d" % (consumer, i),
                "item_id": item,
                "item_consumer": consumer,
                "date": T0 - timedelta(days=1),
                "inc": {"dsk_hours": 0.5},
                "abs": {"dsk_hours": 10.25 + i, "dsk_starts": i, "DHN": 1.5},
            }
            previous[item + "##" + consumer] = {"abs": row["abs"]} if abs_only else row
    return previous


@pytest.fixture
def stubs(monkeypatch):
    from api.services.usage import desktop as desktop_mod
    from api.services.usage.consolidate import ConsolidateProcessed
    from isardvdi_common.lib.usage.desktop import DesktopUsageProcessed

    state = {"rows": _log_rows(), "fields": None, "abs_only": True, "inserted": []}
    monkeypatch.setattr(
        DesktopUsageProcessed,
        "iter_logs",
        classmethod(lambda cls, *a: _fetch(state["rows"], state["fields"])),
    )
    monkeypatch.setattr(
        desktop_mod, "get_abs_consumptions", lambda *a: _previous(state["abs_only"])
    )
    monkeypatch.setattr(desktop_mod, "get_params_item_type_custom", lambda *a: FORMULA)
    monkeypatch.setattr(
        ConsolidateProcessed,
        "get_domains_with_tags",
        classmethod(lambda cls: {t: [{"name": t.upper()}] for t in TEMPLATES}),
    )
    monkeypatch.setattr(
        ConsolidateProcessed,
        "insert_consumption_batch",
        classmethod(lambda cls, data: state["inserted"].extend(copy.deepcopy(data))),
    )
    return state


def _consolidate(state, **overrides):
    from api.services.usage.desktop import ConsolidateDesktopConsumption

    state.update(overrides, inserted=[])
    ConsolidateDesktopConsumption(days_before=1)
    return sorted(state["inserted"], key=lambda row: row["pk"])


def _grouped_first(state):
    """The consolidation as it was done before streaming: group every row per
    consumer, then add each group's consumptions in row order."""
    from api.services.usage import consolidate as mod
    from api.services.usage.desktop import DesktopsUsage

    usage = DesktopsUsage(days_before=1)
    rows = list(_fetch(state["rows"], None))
    base_maker = mod.ConsolidateConsumption.__new__(mod.ConsolidateConsumption)
    base_maker.name = "desktop"
    base_maker.domains = {t: [{"name": t.upper()}] for t in TEMPLATES}
    day = usage.consolidation_day
    previous = _previous(False)
    out = []
    for consumer in usage.consumer_items:
        groups = {}
        for row in rows:
            key = mod.item_key(consumer, row)
            if key is not mod.SKIP:
                groups.setdefault(key, []).append(row)
        for group in groups.values():
            base = base_maker._item_base_data(consumer, group[0], day, "desktop")
            if not base:
                continue
            added = {}
            for row in group:
                added = mod.add_dicts(added, usage._process_consumption(row))
            prev = previous.get(base["item_id"] + "##" + consumer, {}).get("abs", {})
            out.append({**base, "inc": added, "abs": mod.add_dicts(prev, added)})
    return sorted(out, key=lambda row: row["pk"])


def test_streamed_consolidation_matches_grouping_every_row_first(stubs):
    expected = _grouped_first(stubs)

    from isardvdi_common.lib.usage.desktop import LOG_FIELDS

    streamed = _consolidate(stubs, fields=set(LOG_FIELDS), abs_only=True)

    assert {row["item_consumer"] for row in expected} >= set(CONSUMERS)
    assert streamed == expected


@pytest.mark.parametrize("field", ["owner_user_name", "hardware_vcpus", "tag"])
def test_dropping_a_read_field_changes_the_result(stubs, field):
    """Control: the comparison above does see a missing field."""
    from isardvdi_common.lib.usage.desktop import LOG_FIELDS

    expected = _grouped_first(stubs)
    fields = set(LOG_FIELDS) - {field}
    assert _consolidate(stubs, fields=fields) != expected


def test_peak_memory_does_not_grow_with_the_logs_of_the_day(stubs):
    def peak(n):
        stubs["rows"] = _log_rows(n)
        tracemalloc.start()
        _consolidate(stubs, fields=None)
        _, top = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        return top

    peak(300)
    assert peak(30000) < 3 * peak(3000)


def test_an_item_that_raises_drops_only_its_batch(stubs, monkeypatch):
    from api.services.usage.desktop import DesktopsUsage

    real = DesktopsUsage._process_consumption

    def flaky(self, row):
        if row["desktop_id"] == "desk-7":
            raise ValueError("bad row")
        return real(self, row)

    monkeypatch.setattr(DesktopsUsage, "_process_consumption", flaky)
    rows = _consolidate(stubs, rows=_log_rows(n=300, desktops=250))
    desktops = {row["item_id"] for row in rows if row["item_consumer"] == "desktop"}

    # items go in batches of 100 in first-seen order: desk-7 sits in the first
    assert desktops == {"desk-%d" % i for i in range(100, 250)}


def test_a_consumer_key_that_raises_stops_after_the_consumers_before_it(stubs):
    stubs["rows"] = _log_rows()
    del stubs["rows"][5]["hyp_started"]

    with pytest.raises(KeyError):
        _consolidate(stubs)

    assert {row["item_consumer"] for row in stubs["inserted"]} == set(CONSUMERS)
