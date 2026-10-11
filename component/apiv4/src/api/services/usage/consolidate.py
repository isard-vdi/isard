# Usage consolidation orchestrator
# SPDX-License-Identifier: AGPL-3.0-or-later

import logging

log = logging.getLogger("apiv4")

#
#   Copyright © 2023 Josep Maria Viñolas Auquer, Alberto Larraz Dalmases
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

import hashlib
import traceback
from datetime import datetime, timedelta
from time import time

import pytz
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.lib.usage.consolidate import ConsolidateProcessed

# README

## Consolidations will be processed always for the day before execution by default
## This can be changed by setting a greater value for days_before
##
## Consolidations are done in parallel batches of batch_size items per thread.
## Be aware this can be too much for your hardware. If you have a lot of data to
## consolidate, you can increase the number of threads to run in parallel by setting
## a greater value for max_threads. Be aware that this can overload your DB.
##
## Only items that have got changes during the day will be consolidated into database.
## So, there will be gaps between days of consolidated data in database, but views
## functions will fill them with the previous consolidated data.


class ConsolidateConsumption:
    consolidating = []
    # Process-wide tallies reported by run_consolidation.
    inserted_total = 0
    failed_batches = 0

    def __del__(self):
        if "name" in self.__dict__:
            log.info(f"====> FINISHED Consolidating {self.name} consumptions <====")

    def __init__(self, name: str, Usage: type, days_before: int = 1) -> None:
        if name in self.consolidating:
            raise Error("bad_request", "Already consolidating %s" % name)
        self.consolidating.append(name)
        self.name = name
        try:
            self.times = {"start": time()}
            log.info(
                "====> STARTING Consolidating %s consumptions for date %s <===="
                % (self.name, get_relative_date(-days_before))
            )

            if days_before < 1:
                raise Error("bad_request", "days_before must be greater than 1")
            # days_before = 1 will consolidate yesterday.
            # Has to be called after midnight to consolidate the previous day
            self.consolidation_day = get_relative_date(-days_before)

            # Instantiate the Usage class to get the data to consolidate
            self.Usage = Usage(days_before=days_before)
            self.times["get_" + self.name + "_log_data"] = time()
            if not self.Usage.has_data:
                log.info(
                    "--> No data to consolidate. Skipping date %s"
                    % self.consolidation_day
                )
                return
            self.domains = self.get_domains()
            items, failed, rows = self.fold_day_data()
            if not rows:
                log.info(
                    "--> No data to consolidate. Skipping date %s"
                    % self.consolidation_day
                )
                return
            log.info(
                "--> Got %s %s consumptions for date %s and %s previous consumptions"
                % (
                    rows,
                    self.name,
                    self.consolidation_day,
                    len(self.Usage.previous_abs_data),
                )
            )
            self.times["get_" + self.name + "_system_items_data"] = time()
            for consumer in self.Usage.consumer_items:
                if consumer in failed:
                    raise failed[consumer]
                self.process_items(items.pop(consumer), consumer)
        finally:
            if self.name in self.consolidating:
                self.consolidating.remove(self.name)

    def fold_day_data(self) -> tuple[dict, dict, int]:
        """Stream the day into per-consumer items, keeping each failure to re-raise later."""
        consumers = self.Usage.consumer_items
        items = {consumer: {} for consumer in consumers}
        failed = {}
        rows = 0
        for row in self.Usage.day_data:
            rows += 1
            try:
                consumption = self.Usage._process_consumption(row)
            except Exception as exc:
                consumption = exc
            for consumer in consumers:
                if consumer in failed:
                    continue
                try:
                    key = item_key(consumer, row)
                except Exception as exc:
                    failed[consumer] = exc
                    continue
                if key is SKIP:
                    continue
                item = items[consumer].get(key)
                if item is None:
                    try:
                        base = self._item_base_data(
                            consumer, row, self.consolidation_day, self.name
                        )
                    except Exception as exc:
                        base = exc
                    item = items[consumer][key] = [base, {}]
                if isinstance(item[1], Exception):
                    continue
                if isinstance(consumption, Exception):
                    item[1] = consumption
                else:
                    item[1] = add_dicts(item[1], consumption)
        return items, failed, rows

    def get_item_consumption_for_consumer(
        self, item: list, consumer: str
    ) -> dict | None:
        item_base_data, item_day_data_added = item
        if isinstance(item_base_data, Exception):
            raise item_base_data
        if not item_base_data:
            return None
        if isinstance(item_day_data_added, Exception):
            raise item_day_data_added

        item_absolute_consumptions_previous_day = self.Usage.previous_abs_data.get(
            item_base_data["item_id"] + "##" + consumer, {}
        ).get("abs", {})

        # Add absolute consumption from day before for item, only if item_day_data_added is incremental
        if self.Usage.calculations_are_incremental:
            item_absolute_consumptions = add_dicts(
                item_absolute_consumptions_previous_day, item_day_data_added
            )
            # Incremental consumption is the same as absolute consumption for item
            item_increment_consumptions = item_day_data_added
        else:
            # item_day_data it's the absolute consumption for the day
            item_absolute_consumptions = item_day_data_added
            # Substract absolute consumption from day before for item
            item_increment_consumptions = substract_dicts(
                item_absolute_consumptions_previous_day, item_day_data_added
            )
        return {
            **item_base_data,
            **{
                "inc": item_increment_consumptions,
                "abs": item_absolute_consumptions,
            },
        }

    def process_items(self, items: dict, consumer: str) -> None:
        """Consolidate ``items`` in batches; a batch where one item raises is skipped."""
        log.info("--> Processing %s %s %s items" % (len(items), consumer, self.name))
        values = list(items.values())
        items.clear()
        data, inserted = [], 0
        for start in range(0, len(values), BATCH_SIZE):
            try:
                consumptions = [
                    self.get_item_consumption_for_consumer(item, consumer)
                    for item in values[start : start + BATCH_SIZE]
                ]
            except Exception:
                log.error("USAGE consolidate batch raised: %s", traceback.format_exc())
                ConsolidateConsumption.failed_batches += 1
                continue
            data.extend(c for c in consumptions if c)
            if len(data) >= INSERT_SIZE:
                ConsolidateProcessed.insert_consumption_batch(data)
                inserted += len(data)
                data = []
        if data:
            ConsolidateProcessed.insert_consumption_batch(data)
            inserted += len(data)
        ConsolidateConsumption.inserted_total += inserted
        self.times["get_" + self.name + "_batches"] = time()
        log.info(
            "--> Consolidated %s %s %s items in | GET_DATA %.2fs | GET_ITEMS_DATA %.2fs | PROCESS_DATA %.2fs | TOTAL %.2fs",
            consumer,
            self.name,
            inserted,
            self.times["get_" + self.name + "_log_data"] - self.times["start"],
            self.times["get_" + self.name + "_system_items_data"]
            - self.times["get_" + self.name + "_log_data"],
            self.times["get_" + self.name + "_batches"]
            - self.times["get_" + self.name + "_system_items_data"],
            time() - self.times["start"],
        )

    def compute_consumer_totals(self, consumer: str, data: list[dict]) -> dict:
        totals = {"inc": {}, "abs": {}}
        for item in data:
            totals["inc"] = add_dicts(totals["inc"], item["inc"])
            totals["abs"] = add_dicts(totals["abs"], item["abs"])
        return {
            "date": self.consolidation_day,
            "item_id": "_total_",
            "item_type": self.name,
            "item_consumer": consumer,
            "item_consumer_category_id": None,
            "item_name": "[Total]",
            "pk": gen_pk(
                "total",
                self.name,
                consumer,
                self.consolidation_day,
            ),
            **totals,
        }

    def _item_base_data(
        self,
        consumer: str,
        item_day_data: dict,
        consolidation_day: datetime,
        item_type: str,
    ) -> dict | None:
        if consumer == "user":
            data = {
                "date": consolidation_day,
                "item_id": item_day_data["owner_user_id"],
                "item_type": item_type,
                "item_consumer": consumer,
                "item_consumer_category_id": item_day_data["owner_category_id"],
                "item_name": item_day_data["owner_user_name"],
            }
        elif consumer == "group":
            data = {
                "date": consolidation_day,
                "item_id": item_day_data["owner_group_id"],
                "item_type": item_type,
                "item_consumer": consumer,
                "item_consumer_category_id": item_day_data["owner_category_id"],
                "item_name": item_day_data["owner_group_name"],
            }
        elif consumer == "category":
            data = {
                "date": consolidation_day,
                "item_id": item_day_data["owner_category_id"],
                "item_type": item_type,
                "item_consumer": consumer,
                "item_consumer_category_id": item_day_data["owner_category_id"],
                "item_name": item_day_data["owner_category_name"],
            }
        elif consumer == "desktop":
            data = {
                "date": consolidation_day,
                "item_id": item_day_data["desktop_id"],
                "item_type": item_type,
                "item_consumer": consumer,
                "item_consumer_category_id": item_day_data["owner_category_id"],
                "item_name": item_day_data["desktop_name"],
            }
        elif consumer == "deployment":
            if item_day_data.get("deployment_id"):
                deployment_id = item_day_data["deployment_id"]
                deployment_name = item_day_data["deployment_name"]
            else:
                if item_day_data.get("deployment_id") == None:
                    return
                try:
                    deployment = self.get_deployment(item_day_data["desktop_id"])
                    if not deployment or not deployment.get("tag"):
                        return
                    deployment_id = deployment["tag"]
                    deployment_name = deployment["tag_name"]
                except Exception:
                    log.exception(
                        "-->  ERROR CONSOLIDATING: Deployment %s not found",
                        item_day_data["deployment_id"],
                    )
                    return None
            data = {
                "date": consolidation_day,
                "item_id": deployment_id,
                "item_type": item_type,
                "item_consumer": consumer,
                "item_consumer_category_id": item_day_data["owner_category_id"],
                "item_name": deployment_name,
            }
        elif consumer == "template":
            template_id = (
                item_day_data["desktop_template_hierarchy"][-1]
                if item_day_data["desktop_template_hierarchy"]
                else None
            )
            if not template_id:
                return
            try:
                template_name = self.get_template_name(template_id)
            except Exception:
                log.exception(
                    "-->  CRITICAL SYSTEM ERROR CONSOLIDATING: Template %s not found for desktop %s",
                    template_id,
                    item_day_data["desktop_id"],
                )
                return None

            data = {
                "date": consolidation_day,
                "item_id": template_id,
                "item_type": item_type,
                "item_consumer": consumer,
                "item_consumer_category_id": item_day_data["owner_category_id"],
                "item_name": template_name,
            }
        elif consumer == "hypervisor":
            if not item_day_data.get("hyp_started") or not item_day_data["hyp_started"]:
                return
            data = {
                "date": consolidation_day,
                "item_id": item_day_data["hyp_started"],
                "item_type": item_type,
                "item_consumer": consumer,
                "item_consumer_category_id": item_day_data["owner_category_id"],
                "item_name": item_day_data["hyp_started"],
            }
        data["pk"] = gen_pk(
            data["item_id"], data["item_type"], consumer, consolidation_day
        )
        return data

    def get_domains(self) -> dict:
        return ConsolidateProcessed.get_domains_with_tags()

    def get_deployment(self, desktop_id: str) -> dict:
        return self.domains.get(
            desktop_id, [{"tag": "[DELETED]", "tag_name": "[DELETED]"}]
        )[0]

    def get_template_name(self, template_id: str) -> str:
        return self.domains.get(template_id, [{"name": "[DELETED]"}])[0]["name"]


## UTILS
BATCH_SIZE = 100
INSERT_SIZE = 1000
SKIP = object()
ITEM_KEYS = {
    "user": "owner_user_id",
    "group": "owner_group_id",
    "category": "owner_category_id",
    "desktop": "desktop_id",
    "deployment": "deployment_id",
    "hypervisor": "hyp_started",
}


def item_key(consumer: str, row: dict):
    """The item ``row`` counts for under ``consumer``, or ``SKIP``."""
    if consumer == "template":
        hierarchy = row["desktop_template_hierarchy"]
        return hierarchy[-1] if hierarchy else SKIP
    return row[ITEM_KEYS[consumer]]


def add_dicts(dict1: dict, dict2: dict) -> dict:
    result = {}
    for key in dict1.keys():
        if key in dict2.keys():
            result[key] = dict1[key] + dict2[key]
        else:
            result[key] = dict1[key]
    for key in dict2.keys():
        if key not in dict1.keys():
            result[key] = dict2[key]
    return result


def substract_dicts(dict1: dict, dict2: dict) -> dict:
    result = {}
    for key in dict1.keys():
        if key in dict2.keys():
            result[key] = dict1[key] - dict2[key]
        else:
            result[key] = dict1[key]
    for key in dict2.keys():
        if key not in dict1.keys():
            result[key] = dict2[key]
    return result


def get_relative_date(days: int) -> datetime:
    # Data to be processed is relative only to events in server, not at client side (logs)
    # So we need only dates (not times) and insert with UTC timezone (+0) with correct date.
    return datetime.now().astimezone().replace(
        minute=0, hour=0, second=0, microsecond=0, tzinfo=pytz.utc
    ) + timedelta(days=days)


def gen_pk(
    item_id: str, item_type: str, consumer: str, consolidation_day: datetime
) -> str | None:
    try:
        return hashlib.md5(
            bytes(
                str(item_id) + item_type + consumer + consolidation_day.isoformat(),
                "utf-8",
            )
        ).hexdigest()
    except Exception:
        log.exception(
            "--> Error generating pk for %s %s %s %s",
            item_id,
            item_type,
            consumer,
            consolidation_day,
        )
