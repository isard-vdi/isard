#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2026 Josep Maria Viñolas Auquer
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The payloads the previous substring blacklist let through, and the legitimate
rich text it must keep accepting."""

import pytest
from isardvdi_common.helpers.html_validation import find_unsafe_html, first_unsafe_html

# Every one of these passed the ``["<script", "<iframe", "javascript:"]`` check.
BLACKLIST_SURVIVORS = [
    "<img src=x onerror=alert(1)>",
    "<svg onload=alert(1)>",
    "<body onload=alert(1)>",
    "<div OnMouseOver = 'alert(1)'>hover</div>",
    "<input autofocus onfocus=alert(1)>",
    "<a href='JaVaScRiPt:alert(1)'>x</a>",
    "<a href='javascript&#58;alert(1)'>x</a>",
    "<a href='javascript&#x3A;alert(1)'>x</a>",
    "<a href='java\tscript:alert(1)'>x</a>",
    "<a href='java\nscript:alert(1)'>x</a>",
    "<a href='vbscript:msgbox(1)'>x</a>",
    "<a href='data:text/html;base64,PHN2Zz5vbmxvYWQ8L3N2Zz4='>x</a>",
    "< script>alert(1)</script>",
    "<meta http-equiv='refresh' content='0;url=//attacker'>",
    "<object data='//attacker'></object>",
    "<embed src='//attacker'>",
    "<form action='//attacker'><input name='p'></form>",
    "<base href='//attacker/'>",
    "<link rel=stylesheet href='//attacker'>",
]

LEGITIMATE = [
    "<b>Manteniment</b> programat a les 18:00.",
    "<p>El servei es reiniciara.</p><ul><li>Desa la feina</li></ul>",
    "<a href='https://example.org/help'>Mes informacio</a>",
    "<img src='https://example.org/logo.png' alt='logo'>",
    "Consulta les dades: mira l'apartat d'ajuda",
    "<a href='https://example.org/data:text'>enllac</a>",
    "<span style='color:red'>atencio</span>",
    "",
    None,
]


@pytest.mark.parametrize("payload", BLACKLIST_SURVIVORS)
def test_payloads_the_old_blacklist_allowed_are_refused(payload):
    assert find_unsafe_html(payload) is not None


@pytest.mark.parametrize("body", LEGITIMATE)
def test_legitimate_rich_text_is_accepted(body):
    assert find_unsafe_html(body) is None


def test_the_reason_never_echoes_the_payload():
    """The reason travels back in a 400, so it must not carry the input."""
    reason = find_unsafe_html("<img src=x onerror=alert('marker-42')>")
    assert reason and "marker-42" not in reason


def test_first_unsafe_html_reports_the_first_offending_field():
    assert first_unsafe_html("<b>ok</b>", "<svg onload=x>") == "event handler attribute"
    assert first_unsafe_html("<b>ok</b>", "<i>also ok</i>") is None
