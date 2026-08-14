#!/bin/sh
#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Every `v-html` here paints admin-authored HTML, so every one has to go through
# `$sanitize`. A directory-wide check because the way a raw one comes back is a
# merge between two branches that are each correct alone.

set -eu

cd "$(dirname "$0")/.."

raw=$(grep -rn 'v-html' src --include='*.vue' | grep -v '\$sanitize' | grep -v 'eslint-disable' || true)

if [ -n "$raw" ]; then
    echo "ERROR: v-html without \$sanitize -- admin-authored HTML would run as script:" >&2
    echo "$raw" | sed 's/^/  /' >&2
    echo "" >&2
    echo "Wrap the expression: v-html=\"\$sanitize(<expr>)\"" >&2
    exit 1
fi

echo "no-unsanitized-v-html: OK ($(grep -rc 'v-html' src --include='*.vue' | grep -v ':0$' | wc -l) files checked)"
