#
#   Copyright © 2025 Miriam Melina Gamboa Valdez
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

import logging as log
from functools import wraps

from .caches import get_cached_unused_item_timeout_by_op


def get_applied_rule_decorator(get_rules_func):
    def decorator(func):
        @wraps(func)
        def wrapper(payload, *args, **kwargs):
            if callable(get_rules_func):
                rules = get_rules_func(*args, **kwargs)
            else:
                rules = get_rules_func

            if not rules:
                return None

            log.debug("Rules retrieved from get_applied_rule_decorator: %s", rules)

            alloweds = {
                "users": "user",
                "groups": "group",
                "categories": "category",
                "roles": "role",
            }

            for rule in rules:
                for key, value in alloweds.items():
                    if rule["allowed"].get(key) is not False:
                        if (
                            not rule["allowed"][key]
                            or payload.get(f"{value}_id") in rule["allowed"][key]
                        ):
                            return func(rule, payload, *args, **kwargs)
            return False

        return wrapper

    return decorator


@get_applied_rule_decorator(get_cached_unused_item_timeout_by_op)
def get_unused_item_timeout(applied_rule, payload, *args, **kwargs):
    return applied_rule
