#
#   Copyright © 2026 IsardVDI
#
#   This file is part of IsardVDI.
#
#   IsardVDI is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or (at your
#   option) any later version.
#
#   IsardVDI is distributed in the hope that it will be useful, but WITHOUT ANY
#   WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
#   FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
#   details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with IsardVDI. If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

import os

import isardvdi_common.helpers.category as category_mod
from isardvdi_common.helpers.category import Category


def _stub(monkeypatch, tmp_path):
    """A Category instance with a known id but no DB (bypass __init__)."""
    monkeypatch.setattr(category_mod, "LOGO_BASE_PATH", str(tmp_path))
    cat = Category.__new__(Category)
    object.__setattr__(cat, "id", "cat-1")
    return cat


def test_collapsed_path_is_a_separate_file(monkeypatch, tmp_path):
    cat = _stub(monkeypatch, tmp_path)
    assert cat._logo_path("logo").endswith("/cat-1/logo")
    assert cat._logo_path("logo-collapsed").endswith("/cat-1/logo-collapsed")


def test_save_and_delete_collapsed_logo(monkeypatch, tmp_path):
    cat = _stub(monkeypatch, tmp_path)
    cat._save_logo(b"<svg/>", "logo-collapsed")
    p = cat._logo_path("logo-collapsed")
    assert os.path.isfile(p)
    # the expanded logo is untouched by a collapsed save
    assert not os.path.isfile(cat._logo_path("logo"))
    cat._delete_logo("logo-collapsed")
    assert not os.path.isfile(p)


def test_logo_path_rejects_escape(monkeypatch, tmp_path):
    cat = _stub(monkeypatch, tmp_path)
    object.__setattr__(cat, "id", "../escape")
    try:
        cat._logo_path("logo-collapsed")
        assert False, "expected ValueError on path escape"
    except ValueError:
        pass


def test_decode_data_url_sanitizes_collapsed_svg(monkeypatch, tmp_path):
    cat = _stub(monkeypatch, tmp_path)
    svg = (
        b'<svg xmlns="http://www.w3.org/2000/svg" width="4" height="4">'
        b'<script>alert(1)</script><rect width="4" height="4"/></svg>'
    )
    import base64

    data_url = "data:image/svg+xml;base64," + base64.b64encode(svg).decode()
    clean = category_mod._decode_data_url(data_url)
    cat._save_logo(clean, "logo-collapsed")
    on_disk = open(cat._logo_path("logo-collapsed"), "rb").read()
    assert b"<script" not in on_disk.lower()
