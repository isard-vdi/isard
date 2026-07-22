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
import os
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from math import ceil
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

            # Batch size and max threads are set to avoid overloading the DB
            # Batch size is the number of items to consolidate in a single thread
            # Max threads is the number of threads to run in parallel
            # The total number of items to consolidate in parallel is batch_size * max_threads
            # So if batch_size is 1000 and max_threads is 6, 6000 items will be computed in
            # parallel. At the end of each thread computation the data will be updated in bulk
            # in the DB.
            self.batch_size = 1000  # Computations in batch for each thread

            # Take into account your hardware cpu cores. 1.20 is a factor to avoid overloading.
            # 1.20 will launch 5 threads in a 6 core cpu (80% of cpu will be used)
            self.max_threads = ceil(os.cpu_count() / 1.20)

            # Instantiate the Usage class to get the data to consolidate
            self.Usage = Usage(days_before=days_before)
            self.times["get_" + self.name + "_log_data"] = time()
            if not self.Usage.has_data:
                log.info(
                    "--> No data to consolidate. Skipping date %s"
                    % self.consolidation_day
                )
                if self.name in self.consolidating:
                    self.consolidating.remove(self.name)
                return
            log.info(
                "--> Got %s %s consumptions for date %s. Starting %s worker threads with %s items per thread"
                % (
                    len(self.Usage.day_data),
                    self.name,
                    self.consolidation_day,
                    ceil(len(self.Usage.day_data) / self.batch_size),
                    self.batch_size,
                )
            )
            log.info(
                "--> Got %s %s previous consumptions"
                % (len(self.Usage.previous_abs_data), self.name)
            )
            self.domains = self.get_domains()
            self.times["get_" + self.name + "_system_items_data"] = time()
            for consumer in self.Usage.consumer_items:
                self.process_batches(self.group_day_data_by_item(consumer), consumer)
        finally:
            if self.name in self.consolidating:
                self.consolidating.remove(self.name)

    def update_items_consumption(self, items: list, consumer: str) -> list[dict]:
        consumptions = []
        for item in items:
            # Here we have a dict with the item_id and the list of consumptions
            item_consumption = self.get_item_consumption_for_consumer(item, consumer)
            if item_consumption:
                consumptions.append(item_consumption)
        return consumptions

    def get_item_consumption_for_consumer(
        self, item: list, consumer: str
    ) -> dict | None:
        if not self.Usage.has_data:
            return None
        item_base_data = self._item_base_data(
            consumer, item[0], self.consolidation_day, self.name
        )

        if not item_base_data:
            return None
        item_day_data_added = {}
        for item_data in item:
            item_day_data_added = add_dicts(
                item_day_data_added, self.Usage._process_consumption(item_data)
            )

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

    def group_day_data_by_item(self, consumer: str) -> list[list[dict]] | None:
        items = {}
        item_key = None
        if consumer == "user":
            item_key = "owner_user_id"
        if consumer == "group":
            item_key = "owner_group_id"
        if consumer == "category":
            item_key = "owner_category_id"
        if consumer == "desktop":
            item_key = "desktop_id"
        if consumer == "deployment":
            item_key = "deployment_id"
        if consumer == "hypervisor":
            item_key = "hyp_started"

        if item_key:
            for item in self.Usage.day_data:
                if item[item_key] not in items:
                    items[item[item_key]] = []
                items[item[item_key]].append(item)
            return [items[key] for key in items.keys()]

        if consumer == "template":
            item_key = "template_id"

        if item_key:
            for item in self.Usage.day_data:
                if not item["desktop_template_hierarchy"]:
                    # Can't be computed to any template
                    # value is None or empty list
                    continue
                item_value = item["desktop_template_hierarchy"][-1]
                if item_value not in items:
                    items[item_value] = []
                items[item_value].append(item)
            return [items[key] for key in items.keys()]

    # PARALLEL PROCESSING
    def process_batches(self, data_batch: list, consumer: str) -> None:
        # data_batch = data_batch[:100]
        self.batch_size = 100
        batches = [
            data_batch[i : i + self.batch_size]
            for i in range(0, len(data_batch), self.batch_size)
        ]

        # Process each batch in a worker thread. Originally this used
        # ``gevent.spawn`` + ``gevent.joinall``; under apiv4's asyncio
        # worker the join blocked the loop on libev's ``ev_run`` and
        # was a UAF risk per APIV4_THREADING_INCIDENT_ANALYSIS.md
        # §3 Tier-D / §5.7 Pattern C. ThreadPoolExecutor keeps the
        # parallelism without the gevent dependency.
        log.info(
            "--> Adding %s %s jobs to thread pool, processing data.."
            % (consumer, len(batches))
        )
        data = []
        if not batches:
            self.times["get_" + self.name + "_batches"] = time()
            return
        with ThreadPoolExecutor(max_workers=min(10, len(batches))) as pool:
            futures = [
                pool.submit(self.update_items_consumption, batch, consumer)
                for batch in batches
            ]
            batches_processed = []
            for future in futures:
                try:
                    batches_processed.append(future.result())
                except Exception:
                    log.error(
                        "USAGE consolidate batch raised: %s",
                        traceback.format_exc(),
                    )
                    batches_processed.append(None)
        for result in batches_processed:
            if result == None:
                continue
            data = data + result
        self.times["get_" + self.name + "_batches"] = time()
        # data.append(self.compute_consumer_totals(consumer, data))
        ConsolidateProcessed.insert_consumption_batch(data)
        log.info(
            "--> Consolidated %s %s %s items in | GET_DATA %.2fs | GET_ITEMS_DATA %.2fs | PROCESS_DATA %.2fs | TOTAL %.2fs",
            consumer,
            self.name,
            len(data),
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
