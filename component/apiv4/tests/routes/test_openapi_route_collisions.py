# SPDX-License-Identifier: AGPL-3.0-or-later
"""Contract tests for the duplicate-route guard in spec generation.

FastAPI accepts two handlers registered on the same method and path: it
serves the first and documents the last. The spec then describes a
handler that never runs, so every generated client decodes the wrong
response shape. ``gen_openapi._assert_no_route_collisions`` inspects
``app.routes`` (not the spec, where the duplicate has already been
overwritten) and aborts generation instead.
"""

import pytest
from api import app
from gen_openapi import _assert_no_route_collisions


class _Route:
    def __init__(self, path, methods, name):
        self.path = path
        self.methods = methods
        self.name = name
        self.endpoint = None


class _App:
    def __init__(self, routes):
        self.routes = routes


def test_registered_app_has_no_route_collisions():
    _assert_no_route_collisions(app)


def test_same_method_and_path_raises():
    duplicated = _App(
        [
            _Route("/api/v4/admin/items/templates", {"GET"}, "first"),
            _Route("/api/v4/admin/items/templates", {"GET"}, "second"),
        ]
    )

    with pytest.raises(RuntimeError, match="duplicate route registration"):
        _assert_no_route_collisions(duplicated)


def test_same_path_different_methods_is_allowed():
    _assert_no_route_collisions(
        _App(
            [
                _Route("/api/v4/admin/items/templates", {"GET"}, "get"),
                _Route("/api/v4/admin/items/templates", {"POST"}, "post"),
            ]
        )
    )


def test_routes_without_methods_are_ignored():
    _assert_no_route_collisions(
        _App(
            [
                _Route("/static", None, "mount-a"),
                _Route("/static", None, "mount-b"),
            ]
        )
    )
