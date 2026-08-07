# SPDX-License-Identifier: AGPL-3.0-or-later

# This directory holds standalone operator scripts (one-shot RethinkDB
# queries, ad-hoc domain-state tools, etc.), NOT pytest tests. The
# existing files have been renamed `script_*.py` / `*.ipy` / plain names
# to avoid pytest collection, but a contributor may still accidentally
# drop a `test_*.py` here.
#
# This `collect_ignore_glob = ["*"]` entry tells pytest to skip every
# file in this directory regardless of its name, so the engine test
# run never trips over an operator script.

collect_ignore_glob = ["*"]
