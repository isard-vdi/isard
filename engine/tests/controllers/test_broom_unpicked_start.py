"""The broom must not walk past a start nobody ever picked up.

A domain in a transitional status with no hypervisor is normal for the moment
between the request and the engine taking it. It stops being normal when the
engine never saw the change at all — its changes cursor was reconnecting, say —
and the blanket skip on those three statuses is what turned that into "stuck
for ever". The skip now ages out.
"""

from engine.controllers.broom import (
    UNPICKED_START_GRACE_S,
    reap_domain_without_hypervisor,
)

NOW = 1_000_000.0


def _d(status, accessed=None):
    d = {"id": "d1", "status": status}
    if accessed is not None:
        d["accessed"] = accessed
    return d


def test_a_fresh_start_is_left_alone():
    assert not reap_domain_without_hypervisor(_d("Starting", NOW - 5), NOW)


def test_a_start_still_inside_the_grace_is_left_alone():
    assert not reap_domain_without_hypervisor(
        _d("Starting", NOW - UNPICKED_START_GRACE_S + 1), NOW
    )


def test_a_start_nobody_picked_up_is_reaped():
    assert reap_domain_without_hypervisor(
        _d("Starting", NOW - UNPICKED_START_GRACE_S), NOW
    )
    assert reap_domain_without_hypervisor(_d("Starting", NOW - 3600), NOW)


def test_the_other_two_transitional_statuses_age_the_same_way():
    for status in ("Stopping", "StartingPaused"):
        assert not reap_domain_without_hypervisor(_d(status, NOW - 5), NOW)
        assert reap_domain_without_hypervisor(_d(status, NOW - 3600), NOW)


def test_any_other_status_is_reaped_as_before():
    """The statuses that were never skipped must keep being converged
    immediately — this change must not add a grace where there was none."""
    for status in ("Unknown", "CreatingDomain", "Updating", "DiskDeleted"):
        assert reap_domain_without_hypervisor(_d(status), NOW)
        assert reap_domain_without_hypervisor(_d(status, NOW - 1), NOW)


def test_a_row_we_cannot_age_is_left_alone():
    """No timestamp means no evidence. Converging on a guess would fail a
    desktop that is starting perfectly well."""
    assert not reap_domain_without_hypervisor(_d("Starting"), NOW)
    assert not reap_domain_without_hypervisor(_d("Starting", None), NOW)
    assert not reap_domain_without_hypervisor(_d("Starting", "recently"), NOW)


def test_the_broom_loop_asks_the_function_and_not_the_bare_status():
    """The six above pin the function; this pins that the loop calls it.

    Without it, resolving the conflict with the refactor that named the status
    tuple restores the blanket skip at the call site and every test still passes.
    """
    import ast
    import inspect

    import engine.controllers.broom as broom

    tree = ast.parse(inspect.getsource(broom))
    unknown_loops = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.For)
        and isinstance(node.iter, ast.Name)
        and node.iter.id == "DB_DOMAINS_WITHOUT_HYP"
        and any(
            isinstance(call.func, ast.Name)
            and call.func.id == "update_domain_status"
            and call.args
            and isinstance(call.args[0], ast.Constant)
            and call.args[0].value == "Unknown"
            for call in ast.walk(node)
            if isinstance(call, ast.Call)
        )
    ]
    assert len(unknown_loops) == 1, (
        f"expected one loop converging hypervisor-less domains to Unknown, "
        f"got {len(unknown_loops)}"
    )

    called = {
        node.func.id
        for guard in ast.walk(unknown_loops[0])
        if isinstance(guard, ast.If)
        for node in ast.walk(guard.test)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert (
        "reap_domain_without_hypervisor" in called
    ), "the loop skips on a bare status test again; the grace is bypassed"
