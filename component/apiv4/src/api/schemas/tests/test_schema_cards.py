# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pydantic schema tests for ``api/schemas/cards.py``."""

import pytest
from api.schemas.cards import CardResponse, GenerateCardRequest
from pydantic import ValidationError


class TestCardResponse:
    _required = {"id": "c-1", "url": "https://x/c.png", "type": "default"}

    def test_accepts_required(self):
        c = CardResponse(**self._required)
        assert c.id == "c-1"

    @pytest.mark.parametrize("missing", ["id", "url", "type"])
    def test_missing_required_rejected(self, missing):
        payload = {k: v for k, v in self._required.items() if k != missing}
        with pytest.raises(ValidationError):
            CardResponse(**payload)


class TestGenerateCardRequest:
    _required = {"desktop_id": "d-1", "desktop_name": "My Desktop"}

    def test_accepts_required(self):
        c = GenerateCardRequest(**self._required)
        assert c.desktop_id == "d-1"
        assert c.desktop_name == "My Desktop"

    @pytest.mark.parametrize("missing", ["desktop_id", "desktop_name"])
    def test_missing_required_rejected(self, missing):
        payload = {k: v for k, v in self._required.items() if k != missing}
        with pytest.raises(ValidationError):
            GenerateCardRequest(**payload)
