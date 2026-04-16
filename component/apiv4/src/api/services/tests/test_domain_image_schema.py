#
#   Copyright © 2026 Josep Maria Viñolas Auquer, Alberto Larraz Dalmases
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

"""Schema tests for ``DomainImage`` and the optional ``DomainImageFile`` upload payload.

The vue 3 ChangeImageModal sends one of two shapes:
 - existing stock image: ``{id, type='stock'}``
 - user-uploaded file: ``{id, type='user', file: {data, filename}}``

The ``file`` field is intentionally write-only (``exclude=True`` on dump),
so a uploaded image's base64 payload is never echoed back in any response.
"""

import pytest
from api.schemas.domains.hardware import DomainImage, DomainImageFile
from pydantic import ValidationError


def test_domain_image_accepts_stock_image_without_file():
    img = DomainImage(id="1.jpg", type="stock", url="/assets/img/desktops/stock/1.jpg")
    assert img.id == "1.jpg"
    assert img.type == "stock"
    assert img.file is None


def test_domain_image_accepts_user_image_with_file():
    img = DomainImage(
        id="user-image-1",
        type="user",
        file=DomainImageFile(data="iVBORw0KGgo=", filename="my-screenshot.png"),
    )
    assert img.file is not None
    assert img.file.data == "iVBORw0KGgo="
    assert img.file.filename == "my-screenshot.png"


def test_domain_image_dump_excludes_file_payload():
    # The `file` field is write-only — dumped responses must never include
    # the base64 blob (frontend only ever needs id/type/url to render).
    img = DomainImage(
        id="user-image-1",
        type="user",
        file=DomainImageFile(data="iVBORw0KGgo=", filename="my-screenshot.png"),
    )
    dumped = img.model_dump()
    assert "file" not in dumped or dumped.get("file") is None


def test_domain_image_file_requires_both_data_and_filename():
    with pytest.raises(ValidationError):
        DomainImageFile(data="iVBORw0KGgo=")  # filename missing
    with pytest.raises(ValidationError):
        DomainImageFile(filename="x.png")  # data missing


def test_domain_image_rejects_missing_required_fields():
    with pytest.raises(ValidationError):
        DomainImage(type="stock")  # id missing
    with pytest.raises(ValidationError):
        DomainImage(id="x")  # type missing
