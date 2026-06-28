#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Media.resolve_download_path honours the {category} placeholder, mirroring
Storage path assembly. StoragePool is built with ``__new__`` and
``get_by_user_kind`` is monkeypatched so no DB is touched.
"""

from isardvdi_common.models.media import Media
from isardvdi_common.models.storage_pool import StoragePool

MP = "/isard/storage_pools/pool-a"


def _media_pool(media_path, id="pool-a", mountpoint=MP):
    pool = StoragePool.__new__(StoragePool)
    object.__setattr__(pool, "id", id)
    object.__setattr__(pool, "mountpoint", mountpoint)
    object.__setattr__(pool, "paths", {"media": [{"path": media_path, "weight": 100}]})
    return pool


def test_resolve_download_path_token(monkeypatch):
    pool = _media_pool("fast/{category}/media")
    monkeypatch.setattr(
        StoragePool, "get_by_user_kind", classmethod(lambda cls, u, k: pool)
    )
    _pool, path = Media.resolve_download_path("u1", "cat-a", "grp/name", "iso")
    assert path == f"{MP}/fast/cat-a/media/grp/name.iso"


def test_resolve_download_path_legacy(monkeypatch):
    pool = _media_pool("media")
    monkeypatch.setattr(
        StoragePool, "get_by_user_kind", classmethod(lambda cls, u, k: pool)
    )
    _pool, path = Media.resolve_download_path("u1", "cat-a", "grp/name", "iso")
    assert path == f"{MP}/cat-a/media/grp/name.iso"
