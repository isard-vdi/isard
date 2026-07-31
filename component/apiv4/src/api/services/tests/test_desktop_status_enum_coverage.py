# SPDX-License-Identifier: AGPL-3.0-or-later

"""Contract test — ``DesktopStatusEnum`` covers every status a desktop row
can really hold.

``UserDesktop.status`` is typed with the enum and pydantic validates the
whole list at once, so a SINGLE row in a status the enum does not know
makes the owner's entire desktop list fail to serialise. Deleting an item
from the admin Downloads page used to do exactly that: it wrote
``Deleting`` on the domain row, a value the enum lacked.

The statuses belong to other components, so this reads them from their
source of truth rather than restating them here — adding a status there
without an enum entry fails this test instead of a user's list.
"""

import ast
from pathlib import Path

import pytest
from api.schemas.domains.desktops import UserDesktop
from isardvdi_common.schemas.domains import DesktopStatusEnum

_REPO_ROOT = Path(__file__).resolve().parents[6]

# (path, symbol) of each collection of desktop statuses owned elsewhere.
_SOURCES = (
    ("engine/engine/engine/config.py", "TRANSITIONAL_STATUS"),
    ("engine/engine/engine/services/db/domains.py", "status_to_failed"),
    (
        "component/change-handler/src/isardvdi_change_handler/task_results/storage.py",
        "_DOMAIN_PRE_READY_STATUSES",
    ),
)

# Statuses the enum must carry that no live collection declares:
# the pre-merge engine download thread wrote them on domain rows, and
# installs upgraded from those releases still have rows holding them.
_LEGACY_STATUSES = ("Downloaded", "ResetDownloading")

# ``Shutdown`` is listed in TRANSITIONAL_STATUS and swept by the
# hypervisor polling thread, but nothing ever writes it: the name comes
# from libvirt's own event tables (``domEventStrings``), not from the
# domain state machine, which goes Shutting-down -> Stopping -> Stopped.
# Drop this exclusion the day something actually sets it.
_NEVER_WRITTEN = frozenset({"Shutdown"})


def _string_literals(node: ast.AST) -> list[str]:
    """Return the string constants of a literal collection.

    Accepts a list/tuple/set literal and ``frozenset({...})``.
    """
    if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "frozenset":
        if not node.args:
            return []
        return _string_literals(node.args[0])
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return [
            element.value
            for element in node.elts
            if isinstance(element, ast.Constant) and isinstance(element.value, str)
        ]
    raise AssertionError(f"unsupported literal node: {ast.dump(node)[:120]}")


def _declared_statuses(path: str, symbol: str) -> list[str]:
    tree = ast.parse((_REPO_ROOT / path).read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == symbol
            for target in node.targets
        ):
            return _string_literals(node.value)
    raise AssertionError(f"{symbol} not found in {path}")


@pytest.mark.parametrize("path,symbol", _SOURCES)
def test_enum_covers_statuses_declared_elsewhere(path: str, symbol: str) -> None:
    source = _REPO_ROOT / path
    if not source.exists():
        pytest.skip(f"{path} absent — this test needs a full repo checkout")
    known = {status.value for status in DesktopStatusEnum}
    declared = set(_declared_statuses(path, symbol)) - _NEVER_WRITTEN
    missing = sorted(declared - known)
    assert not missing, (
        f"{symbol} ({path}) declares {missing}, absent from DesktopStatusEnum. "
        "A desktop row in one of those statuses breaks the whole list it appears in."
    )


@pytest.mark.parametrize("status", _LEGACY_STATUSES)
def test_enum_covers_legacy_statuses(status: str) -> None:
    assert status in {member.value for member in DesktopStatusEnum}


@pytest.mark.parametrize(
    "status", ["Deleting", "Downloaded", "DiskDeleted", "DeletingDomainDisk"]
)
def test_user_desktop_serialises_a_row_in_a_download_lifecycle_status(
    status: str,
) -> None:
    """The regression itself: one such row must not break the model."""
    desktop = UserDesktop(
        id="a-desktop",
        name="A desktop",
        status=status,
        type="persistent",
        viewers=[],
        user="a-user",
        group="a-group",
        category="a-category",
        interfaces=[],
        storage=[],
    )
    assert desktop.model_dump(mode="json")["status"] == status
