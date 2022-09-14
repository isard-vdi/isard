#!flask/bin/python
# coding=utf-8
import json

from api import app

from ..libv2.api_stats import (
    CategoriesKindState,
    CategoriesLimitsHardware,
    Desktops,
    GroupByCategories,
    KindState,
    OtherStatus,
    Templates,
    Users,
)
from .decorators import is_admin


@app.route("/api/v3/stats", methods=["GET"])
@is_admin
def stats_general(payload):
    return (
        json.dumps(
            {
                "users": Users(),
                "desktops": Desktops(),
                "templates": Templates(),
            }
        ),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/stats/<kind>", methods=["GET"])
@app.route("/api/v3/stats/<kind>/<state>", methods=["GET"])
@is_admin
def stats_kind_state(payload, kind, state=False):
    if state == False:
        KindState(kind)
    else:
        KindState(kind, state)
    return (
        json.dumps({"query": KindState(kind, state)}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/stats/category/status", methods=["GET"])
@is_admin
def stats_kind_status(payload):
    return (
        json.dumps({"categories": OtherStatus()}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/stats/categories", methods=["GET"])
@is_admin
def stats_categories(payload):
    return (
        json.dumps({"category": GroupByCategories()}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/stats/categories/<kind>", methods=["GET"])
@app.route("/api/v3/stats/categories/<kind>/<state>", methods=["GET"])
@is_admin
def stats_categories_kind_state(payload, kind, state=False):
    if state == False:
        CategoriesKindState(kind)
    else:
        CategoriesKindState(kind, state)
    return (
        json.dumps({"category": CategoriesKindState(kind, state)}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/stats/categories/limits", methods=["GET"])
@is_admin
def stats_categories_limits(payload):
    return (
        json.dumps({"category": CategoriesLimitsHardware()}),
        200,
        {"Content-Type": "application/json"},
    )
