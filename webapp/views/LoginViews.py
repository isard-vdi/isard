#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright 2018 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
#      Néfix Estrada Campañá
# License: AGPLv3

from flask import request, flash, redirect, url_for, render_template
from flask_login import login_user, logout_user, login_required, current_user

from webapp import app
from ..auth.auth import initialize_kinds
from ..models.user import User
from ..auth.exceptions import AuthException, Disabled


@app.route("/")
def index():
    if current_user.is_authenticated:
        if current_user.is_admin:
            return redirect(url_for("admin"))

    if "X-Forwarded-For" in request.headers:
        remote_addr = request.headers["X-Forwarded-For"].split(",")[0]

    else:
        remote_addr = request.remote_addr.split(",")[0]

    disposables = app.isardapi.show_disposable(remote_addr)

    return render_template(
        "login_disposables.html", disposables=disposables if disposables else ""
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form["user"] == "" or request.form["password"] == "":
            flash("Can't leave blanks", "danger")

        elif request.form["user"].startswith(" "):
            flash("Usernames can't start with an empty space", "warning")

        else:
            user = User()
            try:
                user.get(request.form["user"])

            except User.NotFound:
                kinds = initialize_kinds()

                for kind in kinds:
                    if kind != "local":
                        user = User(kinds[kind].get_user(request.form["user"]))

                        try:
                            authenticated = user.auth(request.form["password"])

                        except User.NotLoaded:
                            pass

                        else:
                            if authenticated:
                                user.create()

                                user.update_access()
                                login_user(user)

                                flash("Logged in successfully", "success")

                                if user.is_admin:
                                    return redirect(url_for("admin"))

                                return redirect(url_for("desktops"))

                flash("User not found", "warning")

            else:
                try:
                    authenticated = user.auth(request.form["password"])

                except AuthException as e:
                    if isinstance(e, Disabled):
                        flash(
                            "The "
                            + user.kind
                            + " authentication or this specific user are disabled",
                            "danger",
                        )

                    else:
                        flash(
                            "Unexpected error when authenticating the user. Try again",
                            "warning",
                        )

                else:
                    if authenticated:
                        user.update_access()
                        login_user(user)

                        flash("Logged in successfully", "success")

                        if user.is_admin:
                            return redirect(url_for("admin"))

                        return redirect(url_for("desktops"))

                    else:
                        flash("Incorrect password", "warning")

    if "X-Forwarded-For" in request.headers:
        remote_addr = request.headers["X-Forwarded-For"].split(",")[0]

    else:
        remote_addr = request.remote_addr.split(",")[0]

    disposables = app.isardapi.show_disposable(remote_addr)

    return render_template(
        "login_disposables.html", disposables=disposables if disposables else ""
    )


@app.route("/logout")
@login_required
def logout():
    logout_user()

    return redirect(url_for("index"))
