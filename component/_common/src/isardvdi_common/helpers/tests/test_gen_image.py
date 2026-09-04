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

import isardvdi_common.helpers.gen_image as gen_image

CARD_SIZE = (480, 248)


def _fits(font, lines):
    return (
        max(font.getlength(line) for line in lines) <= CARD_SIZE[0]
        and len(lines) * sum(font.getmetrics()) <= CARD_SIZE[1]
    )


def test_short_name_uses_the_biggest_size():
    font, lines = gen_image.fit_text("Ubuntu", CARD_SIZE)
    assert lines == ["Ubuntu"]
    assert font.size == gen_image.MAX_FONT_SIZE
    assert _fits(font, lines)


def test_long_name_shrinks_but_stays_readable():
    font, lines = gen_image.fit_text(
        "Debian 12 escriptori de proves molt llarg amb text extra", CARD_SIZE
    )
    assert 1 < len(lines) <= gen_image.MAX_LINES
    assert font.size >= gen_image.MIN_FONT_SIZE
    assert _fits(font, lines)


def test_font_fallback_is_sized(monkeypatch):
    # Without this the fallback is a bitmap font that renders unreadably small.
    monkeypatch.setattr(gen_image, "_FONT_CANDIDATES", ())
    font, lines = gen_image.fit_text("Windows 11 Pro", CARD_SIZE)
    assert font.size >= gen_image.MIN_FONT_SIZE
    assert _fits(font, lines)
