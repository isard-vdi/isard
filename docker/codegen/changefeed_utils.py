# SPDX-License-Identifier: AGPL-3.0-or-later


def camel(name: str) -> str:
    """Convert a snake_case table name to CamelCase."""
    return "".join(p.capitalize() for p in name.split("_"))
