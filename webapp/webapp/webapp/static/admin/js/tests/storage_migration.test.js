// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Functional regression tests for the admin storage-migration JS. The webapp
// admin JS has no CI test harness yet, so run this directly:
//
//   docker run --rm -v "$PWD:/app" -w /app node:lts \
//     node webapp/webapp/webapp/static/admin/js/tests/storage_migration.test.js
//
// Covered:
//   * migEscape (guard-3): attribute-injection XSS — & < > " ' all escaped.
//   * migSelection: emits the right selection per kind (pool / path / category).
//   * migCreateConfig: days-of-week + recurring ride into the window/config.
//
// The file references jQuery/socket globals at load time, so we extract the pure
// functions by source and evaluate them against a tiny jQuery stub.

const fs = require("fs");
const assert = require("assert");
const path = require("path");

const SRC = path.join(__dirname, "..", "storage_migration.js");
const src = fs.readFileSync(SRC, "utf8");

function extract (name) {
  // Grab a top-level `function name (...) { ... }` up to its column-0 closing
  // brace (inner braces are indented, so `\n}` matches only the function end).
  const re = new RegExp("function " + name + "\\s*\\([^)]*\\)\\s*\\{[\\s\\S]*?\\n\\}");
  const m = src.match(re);
  assert(m, name + " function not found in storage_migration.js");
  return m[0];
}

// --------------------------------------------------------------------------- //
// migEscape (guard-3)
// --------------------------------------------------------------------------- //
const migEscape = eval("(" + extract("migEscape").replace(/^function migEscape/, "function") + ")");

assert.strictEqual(migEscape("<b>&</b>"), "&lt;b&gt;&amp;&lt;/b&gt;");
const dq = '" autofocus onfocus=alert(1) x="';
assert(!migEscape(dq).includes('"'), "double quote not escaped");
assert(migEscape(dq).includes("&quot;"), "expected &quot;");
const sq = "' onmouseover='alert(1)";
assert(!migEscape(sq).includes("'"), "single quote not escaped");
assert(migEscape(sq).includes("&#39;"), "expected &#39;");
assert.strictEqual(migEscape(null), "");
assert.strictEqual(migEscape(undefined), "");
console.log("migEscape guard-3 XSS regression: PASS");

// --------------------------------------------------------------------------- //
// migSelection / migCreateConfig — build the pure functions over a jQuery stub
// --------------------------------------------------------------------------- //
function makeJQ (fixture) {
  return function q (sel) {
    if (typeof sel !== "string") {
      // $(this) inside .each() -> the element carries its .value
      return { val: function () { return sel.value; } };
    }
    return {
      val: function () { return (fixture.vals && fixture.vals[sel]) || ""; },
      is: function () { return !!(fixture.checks && fixture.checks[sel]); },
      find: function () {
        return {
          each: function (cb) {
            (fixture.days || []).forEach(function (d) { cb.call({ value: d }); });
          }
        };
      }
    };
  };
}

const bundle = [
  extract("migDaysFrom"),
  extract("migWindowFrom"),
  extract("migSelection"),
  extract("migCreateConfig")
].join("\n");
const factory = new Function(
  "$",
  bundle +
    "\nreturn { migSelection: migSelection, migCreateConfig: migCreateConfig };"
);
function api (fixture) { return factory(makeJQ(fixture)); }

// pool kind
let a = api({ vals: { "#mig_kind": "pool", "#mig_src_pool": "src", "#mig_dst_pool": "dst" } });
assert.deepStrictEqual(a.migSelection(), { kind: "pool", src_pool_id: "src", dst_pool_id: "dst" });

// path kind
a = api({
  vals: {
    "#mig_kind": "path", "#mig_src_pool": "src",
    "#mig_path_prefix": "/isard/fast", "#mig_dst_pool": "dst"
  }
});
assert.deepStrictEqual(a.migSelection(), {
  kind: "path", src_pool_id: "src", path_prefix: "/isard/fast", dst_pool_id: "dst"
});

// category kind
a = api({ vals: { "#mig_kind": "category", "#mig_category": "cat1", "#mig_dst_pool": "dst" } });
assert.deepStrictEqual(a.migSelection(), { kind: "category", category_id: "cat1", dst_pool_id: "dst" });
console.log("migSelection per-kind: PASS");

// migCreateConfig: recurring + days-of-week + time window + cadence/failure
a = api({
  vals: {
    "#mig_bwlimit": "100", "#mig_parallel": "2",
    "#mig_win_start": "22:00", "#mig_win_end": "06:00",
    "#mig_rescan_cadence": "continuous", "#mig_failure_policy": "pause",
    "#mig_quarantine_after": "5"
  },
  checks: { "#mig_verify": true, "#mig_recurring": true, "#mig_force_stop": false },
  days: [5, 6]
});
let cfg = a.migCreateConfig();
assert.strictEqual(cfg.recurring, true, "recurring must ride into config");
assert.strictEqual(cfg.bwlimit_kbs, 100);
assert.strictEqual(cfg.parallelism, 2);
assert.deepStrictEqual(cfg.window, { tz: "UTC", start: "22:00", end: "06:00", days: [5, 6] });
assert.strictEqual(cfg.rescan_cadence, "continuous");
assert.strictEqual(cfg.failure_policy, "pause");
assert.strictEqual(cfg.quarantine_after, 5);

// days-only window (no time range) is still a window
a = api({ vals: {}, checks: {}, days: [0, 1, 2, 3, 4] });
cfg = a.migCreateConfig();
assert.deepStrictEqual(cfg.window, { tz: "UTC", days: [0, 1, 2, 3, 4] });
assert.strictEqual(cfg.recurring, false);

// no schedule at all -> null window
a = api({ vals: {}, checks: {}, days: [] });
assert.strictEqual(a.migCreateConfig().window, null);
console.log("migCreateConfig days + recurring: PASS");

console.log("ALL PASS");
