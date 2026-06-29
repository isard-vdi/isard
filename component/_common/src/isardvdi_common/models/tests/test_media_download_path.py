#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Media.resolve_download_path places the media file FLAT by media-id under the
pool's per-usage media directory, mirroring how Storage names its disks (and how
main stores media: ``/isard/media/<id>.<kind>``). The pool layout owns category
placement (legacy ``<mp>/<cat>/media``, the ``{category}`` token, or none for the
default pool); the on-disk leaf is always ``<media_id>.<kind>`` -- never the
nested ``cat/group/provider/user/name`` urlpath, which is kept only as the media
``path`` label. StoragePool is built with ``__new__`` and ``get_by_user_kind`` is
monkeypatched so no DB is touched.
"""

from isardvdi_common.helpers.default_storage_pool import DEFAULT_STORAGE_POOL_ID
from isardvdi_common.models.media import Media
from isardvdi_common.models.storage_pool import StoragePool

MP = "/isard/storage_pools/pool-a"
MEDIA_ID = "11111111-2222-3333-4444-555555555555"


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
    _pool, path = Media.resolve_download_path(
        "u1", "cat-a", media_id=MEDIA_ID, kind="iso"
    )
    assert path == f"{MP}/fast/cat-a/media/{MEDIA_ID}.iso"


def test_resolve_download_path_legacy_category_appears_once(monkeypatch):
    pool = _media_pool("media")
    monkeypatch.setattr(
        StoragePool, "get_by_user_kind", classmethod(lambda cls, u, k: pool)
    )
    _pool, path = Media.resolve_download_path(
        "u1", "cat-a", media_id=MEDIA_ID, kind="iso"
    )
    assert path == f"{MP}/cat-a/media/{MEDIA_ID}.iso"
    # Regression: the category segment must appear EXACTLY ONCE (it used to be
    # duplicated -- once from build_category_pool_dir, once from the urlpath).
    assert path.count("/cat-a/") == 1


def test_resolve_download_path_default_pool_has_no_category(monkeypatch):
    pool = _media_pool(
        "media", id=DEFAULT_STORAGE_POOL_ID, mountpoint="/isard/storage_pools/default"
    )
    monkeypatch.setattr(
        StoragePool, "get_by_user_kind", classmethod(lambda cls, u, k: pool)
    )
    _pool, path = Media.resolve_download_path(
        "u1", "cat-a", media_id=MEDIA_ID, kind="iso"
    )
    # Default pool mirrors default-pool disks: flat, no per-category subdir.
    assert path == f"/isard/storage_pools/default/media/{MEDIA_ID}.iso"
