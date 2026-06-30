// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Functional regression test for migEscape (guard-3). The webapp admin JS has
// no CI test harness yet, so run this directly:
//
//   docker run --rm -v "$PWD:/app" -w /app node:lts \
//     node webapp/webapp/webapp/static/admin/js/tests/storage_migration.test.js
//
// migEscape only escaped & < > — admin-set values reflected into double-quoted
// HTML attributes (window HH:MM, ids) could break out of the attribute with a
// payload like `" autofocus onfocus=alert(1)` -> attribute-injection XSS. It
// now also escapes " and '.

const fs = require("fs");
const assert = require("assert");
const path = require("path");

const SRC = path.join(__dirname, "..", "storage_migration.js");
const src = fs.readFileSync(SRC, "utf8");

// Extract just the migEscape declaration (the file references jQuery/socket
// globals at load time, so we cannot require the whole module under node).
const match = src.match(/function migEscape\s*\([^)]*\)\s*\{[\s\S]*?\n\}/);
assert(match, "migEscape function not found in storage_migration.js");
const migEscape = eval("(" + match[0].replace(/^function migEscape/, "function") + ")");

// text escaping still works
assert.strictEqual(migEscape("<b>&</b>"), "&lt;b&gt;&amp;&lt;/b&gt;");

// guard-3: the attribute-breakout payload must not survive
const dq = '" autofocus onfocus=alert(1) x="';
const outDq = migEscape(dq);
assert(!outDq.includes('"'), "double quote not escaped: " + outDq);
assert(outDq.includes("&quot;"), "expected &quot; in output: " + outDq);

const sq = "' onmouseover='alert(1)";
const outSq = migEscape(sq);
assert(!outSq.includes("'"), "single quote not escaped: " + outSq);
assert(outSq.includes("&#39;"), "expected &#39; in output: " + outSq);

// null/undefined safe
assert.strictEqual(migEscape(null), "");
assert.strictEqual(migEscape(undefined), "");

console.log("migEscape guard-3 XSS regression: PASS");
