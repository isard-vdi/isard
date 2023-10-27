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

from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone

from cachetools import TTLCache, cached
from rethinkdb import RethinkDB

from api import app

from .flask_rethink import RDB

r = RethinkDB()
db = RDB(app)
db.init_app(app)


def _get_table_indexs():
    indexs = {}
    with app.app_context():
        for table in r.table_list().run(db.conn):
            indexs[table] = r.table(table).index_list().run(db.conn)
    return indexs


TABLE_INDEXS = _get_table_indexs()


class DatatablesQuery(ABC):
    @property
    @abstractmethod
    def _table(self):
        pass

    def __init__(self, form_data):
        self.form_data = self.parse_multi_form(form_data)
        self.q = None
        self.skip_indexs = False

    def default_query(self):
        if not self.q:
            self.q = r.table(self._table)
            self.q = self.add_order()
            self.q = self.add_range_filters()
            self.q = self.add_search_filters()
            self.q = self.add_pluck()

    @property
    def query(self):
        return self.q

    @query.setter
    def query(self, query):
        self.q = query

    @property
    @cached(cache=TTLCache(maxsize=1, ttl=5))
    def total(self):
        with app.app_context():
            return r.table(self._table).count().run(db.conn)

    @property
    @cached(cache=TTLCache(maxsize=1, ttl=5))
    def filtered(self):
        self.default_query()
        with app.app_context():
            return self.q.count().run(db.conn)

    @property
    @cached(cache=TTLCache(maxsize=1, ttl=5))
    def data_filtered(self):
        self.default_query()
        with app.app_context():
            return list(self.q.run(db.conn))

    @property
    @cached(cache=TTLCache(maxsize=1, ttl=5))
    def data_paged(self):
        self.default_query()
        query = self.add_pagination(self.q)
        with app.app_context():
            return list(query.run(db.conn))

    @property
    def data(self):
        return {
            "draw": int(self.form_data["draw"]),
            "recordsTotal": self.total,
            "recordsFiltered": self.filtered,
            "data": self.data_paged,
            "indexs": TABLE_INDEXS[self._table],
        }

    def add_order(self, custom_query=None, skip_indexs=False):
        if not custom_query:
            custom_query = self.q
        if not len(self.form_data["order"]):
            return custom_query
        order_field = self.form_data["columns"][
            int(self.form_data["order"][0]["column"])
        ]["data"]
        if not skip_indexs:
            if (
                len(self.form_data["order"]) == 1
                and order_field in TABLE_INDEXS[self._table]
            ):
                if self.form_data["order"][0]["dir"] == "desc":
                    custom_query = custom_query.order_by(index=r.desc(order_field))
                else:
                    custom_query = custom_query.order_by(index=r.asc(order_field))
                if order_field != self.form_data["range"]["field"]:
                    self.skip_indexs = True
                return custom_query
        for key, order in self.form_data["order"].items():
            if order["dir"] == "desc":
                custom_query = custom_query.order_by(
                    r.desc(self.form_data["columns"][int(order["column"])]["data"])
                )
            else:
                custom_query = custom_query.order_by(
                    r.asc(self.form_data["columns"][int(order["column"])]["data"])
                )

        return custom_query

    def add_search_filters(self, custom_query=None):
        if not custom_query:
            custom_query = self.q
        for _, column in self.form_data["columns"].items():
            if column["data"] != "" and column["search"]["value"] != "":
                # filter[column["data"]] = column["search"]["value"]
                custom_query = custom_query.filter(
                    lambda doc: doc[column["data"]].match(column["search"]["value"])
                )
        return custom_query

    def add_range_filters(self, custom_query=None, skip_indexs=False):
        if not custom_query:
            custom_query = self.q
        if self.form_data.get("range"):
            if skip_indexs or self.skip_indexs:
                custom_query = custom_query.filter(
                    lambda doc: doc[self.form_data["range"]["field"]].during(
                        r.time(
                            r.iso8601(self.form_data["range"]["start"] + "Z").year(),
                            r.iso8601(self.form_data["range"]["start"] + "Z").month(),
                            r.iso8601(self.form_data["range"]["start"] + "Z").day(),
                            r.iso8601(self.form_data["range"]["start"] + "Z").hours(),
                            r.iso8601(self.form_data["range"]["start"] + "Z").minutes(),
                            r.iso8601(self.form_data["range"]["start"] + "Z").seconds(),
                            "Z",
                        ),
                        r.time(
                            r.iso8601(self.form_data["range"]["end"] + "Z").year(),
                            r.iso8601(self.form_data["range"]["end"] + "Z").month(),
                            r.iso8601(self.form_data["range"]["end"] + "Z").day(),
                            r.iso8601(self.form_data["range"]["end"] + "Z").hours(),
                            r.iso8601(self.form_data["range"]["end"] + "Z").minutes(),
                            r.iso8601(self.form_data["range"]["end"] + "Z").seconds(),
                            "Z",
                        ),
                    )
                )
            else:
                custom_query = custom_query.between(
                    r.time(
                        r.iso8601(self.form_data["range"]["start"] + "Z").year(),
                        r.iso8601(self.form_data["range"]["start"] + "Z").month(),
                        r.iso8601(self.form_data["range"]["start"] + "Z").day(),
                        r.iso8601(self.form_data["range"]["start"] + "Z").hours(),
                        r.iso8601(self.form_data["range"]["start"] + "Z").minutes(),
                        r.iso8601(self.form_data["range"]["start"] + "Z").seconds(),
                        "Z",
                    ),
                    r.time(
                        r.iso8601(self.form_data["range"]["end"] + "Z").year(),
                        r.iso8601(self.form_data["range"]["end"] + "Z").month(),
                        r.iso8601(self.form_data["range"]["end"] + "Z").day(),
                        r.iso8601(self.form_data["range"]["end"] + "Z").hours(),
                        r.iso8601(self.form_data["range"]["end"] + "Z").minutes(),
                        r.iso8601(self.form_data["range"]["end"] + "Z").seconds(),
                        "Z",
                    ),
                    index=self.form_data["range"]["field"],
                )

        return custom_query

    def add_pagination(self, custom_query=None):
        if not custom_query:
            custom_query = self.q
        custom_query = custom_query.skip(int(self.form_data["start"])).limit(
            int(self.form_data["length"])
        )
        return custom_query

    def add_pluck(self, custom_query=None):
        if not custom_query:
            custom_query = self.q
        if self.form_data.get("pluck"):
            custom_query = custom_query.pluck(self.form_data["pluck"])
        return custom_query

    def parse_multi_form(self, form_data):
        data = {}
        for url_k in form_data:
            v = form_data[url_k]
            ks = []
            while url_k:
                if "[" in url_k:
                    k, r = url_k.split("[", 1)
                    ks.append(k)
                    if r[0] == "]":
                        ks.append("")
                    url_k = r.replace("]", "", 1)
                else:
                    ks.append(url_k)
                    break
            sub_data = data
            for i, k in enumerate(ks):
                if k.isdigit():
                    k = int(k)
                if i + 1 < len(ks):
                    if not isinstance(sub_data, dict):
                        break
                    if k in sub_data:
                        sub_data = sub_data[k]
                    else:
                        sub_data[k] = {}
                        sub_data = sub_data[k]
                else:
                    if isinstance(sub_data, dict):
                        sub_data[k] = v
        return data


class LogsDesktopsQuery(DatatablesQuery):
    _table = "logs_desktops"

    def __init__(self, form_data):
        super().__init__(form_data)

    @property
    def desktop_view(self):
        self.group_by_desktop_name()

    def group_by_desktop_name(self):
        query = r.table(self._table)
        # query = self.add_range_filters(query)
        query = (
            query.group(index="desktop_id")
            .map(
                lambda log: {
                    "count": 1,
                    "desktop_name": log["desktop_name"],
                    "desktop_id": log["desktop_id"],
                    "owner_user_name": log["owner_user_name"],
                    "owner_user_id": log["owner_user_id"],
                    "owner_group_name": log["owner_group_name"],
                    "owner_group_id": log["owner_group_id"],
                    "owner_category_name": log["owner_category_name"],
                    "owner_category_id": log["owner_category_id"],
                    "starting_time": log["starting_time"],
                }
            )
            .reduce(
                lambda left, right: {
                    "count": left["count"] + right["count"],
                    "desktop_name": left["desktop_name"],
                    "desktop_id": left["desktop_id"],
                    "owner_user_name": left["owner_user_name"],
                    "owner_user_id": left["owner_user_id"],
                    "owner_group_name": left["owner_group_name"],
                    "owner_group_id": left["owner_group_id"],
                    "owner_category_name": left["owner_category_name"],
                    "owner_category_id": left["owner_category_id"],
                    "starting_time": right["starting_time"],
                }
            )
            .ungroup()["reduction"]
        )

        query = self.add_order(query, skip_indexs=True)
        query = self.add_range_filters(query, skip_indexs=True)
        query = self.add_search_filters(query)
        query = self.add_pluck(query)
        self.query = query


class LogsUsersQuery(DatatablesQuery):
    _table = "logs_users"

    def __init__(self, form_data):
        super().__init__(form_data)

    @property
    def user_view(self):
        self.group_by_user_name()

    def group_by_user_name(self):
        query = r.table(self._table)
        # query = self.add_range_filters(query)
        query = (
            query.group(index="owner_user_id")
            .map(
                lambda log: {
                    "count": 1,
                    "owner_user_name": log["owner_user_name"],
                    "owner_user_id": log["owner_user_id"],
                    "owner_group_name": log["owner_group_name"],
                    "owner_group_id": log["owner_group_id"],
                    "owner_category_name": log["owner_category_name"],
                    "owner_category_id": log["owner_category_id"],
                    "started_time": log["started_time"],
                }
            )
            .reduce(
                lambda left, right: {
                    "count": left["count"] + right["count"],
                    "owner_user_name": left["owner_user_name"],
                    "owner_user_id": left["owner_user_id"],
                    "owner_group_name": left["owner_group_name"],
                    "owner_group_id": left["owner_group_id"],
                    "owner_category_name": left["owner_category_name"],
                    "owner_category_id": left["owner_category_id"],
                    "started_time": right["started_time"],
                }
            )
            .ungroup()["reduction"]
        )

        query = self.add_order(query, skip_indexs=True)
        query = self.add_range_filters(query, skip_indexs=True)
        query = self.add_search_filters(query)
        query = self.add_pluck(query)
        self.query = query
