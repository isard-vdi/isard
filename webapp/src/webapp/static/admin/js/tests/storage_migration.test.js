// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Functional regression tests for the admin storage-migration JS. Run by
// `make ci-test-webapp-js`, or directly with `bun <this file>`.
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
      // migItemKinds reads the ticked disk-type boxes as $(sel).map(..).get()
      map: function (cb) {
        const out = (fixture.itemKinds || []).map(function (k) {
          return cb.call({ value: k });
        });
        return { get: function () { return out; } };
      },
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
  extract("migItemKinds"),
  extract("migSelection"),
  // migCreateConfig calls these, so the bundle needs them or the file dies at
  // the first migCreateConfig assertion with a bare ReferenceError
  extract("migGbToBytes"),
  extract("migUsageAgeUnitDays"),
  extract("migUsageAgeDays"),
  extract("migAgeConfig"),
  extract("migLoadPolicyObj"),
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
assert.deepStrictEqual(a.migSelection(),
  { kind: "pool", src_pool_id: "src", dst_pool_id: "dst", item_kinds: [] });

// path kind
a = api({
  vals: {
    "#mig_kind": "path", "#mig_src_pool": "src",
    "#mig_path_prefix": "/isard/fast", "#mig_dst_pool": "dst"
  }
});
assert.deepStrictEqual(a.migSelection(), {
  kind: "path", src_pool_id: "src", path_prefix: "/isard/fast", dst_pool_id: "dst",
  item_kinds: []
});

// category kind
a = api({ vals: { "#mig_kind": "category", "#mig_category": "cat1", "#mig_dst_pool": "dst" } });
assert.deepStrictEqual(a.migSelection(),
  { kind: "category", category_id: "cat1", dst_pool_id: "dst", item_kinds: [] });
console.log("migSelection per-kind: PASS");

// disk types: none ticked == all of them (empty list), and a ticked subset
// travels in the selection so the plan preview and the job agree.
a = api({
  vals: { "#mig_kind": "pool", "#mig_src_pool": "src", "#mig_dst_pool": "dst" },
  itemKinds: ["desktop"]
});
assert.deepStrictEqual(a.migSelection(), {
  kind: "pool", src_pool_id: "src", dst_pool_id: "dst", item_kinds: ["desktop"]
});
console.log("migSelection item_kinds: PASS");

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

// order: absent -> "none" (today's behaviour), and a chosen value travels
a = api({ vals: { "#mig_parallel": "1", "#mig_bwlimit": "0" } });
assert.strictEqual(a.migCreateConfig().order, "none");
a = api({ vals: { "#mig_parallel": "1", "#mig_bwlimit": "0", "#mig_order": "oldest_first" } });
assert.strictEqual(a.migCreateConfig().order, "oldest_first");
console.log("migCreateConfig order: PASS");

// min_free_pct: the form defaults it to 10, and a chosen value travels.
a = api({ vals: { "#mig_min_free_pct": "10" } });
assert.strictEqual(a.migCreateConfig().min_free_pct, 10);
a = api({ vals: { "#mig_min_free_pct": "25" } });
assert.strictEqual(a.migCreateConfig().min_free_pct, 25);
console.log("migCreateConfig min_free_pct: PASS");

// usage_age_days: only travels with an order (the API rejects it with none),
// and days/weeks/months convert to days.
a = api({ vals: { "#mig_order": "oldest_first", "#mig_usage_age_value": "7", "#mig_usage_age_unit": "days" } });
assert.strictEqual(a.migCreateConfig().usage_age_days, 7);
a = api({ vals: { "#mig_order": "newest_first", "#mig_usage_age_value": "2", "#mig_usage_age_unit": "weeks" } });
assert.strictEqual(a.migCreateConfig().usage_age_days, 14);
// a threshold with no order is dropped rather than sent (would be a 400)
a = api({ vals: { "#mig_order": "none", "#mig_usage_age_value": "7" } });
assert.strictEqual(a.migCreateConfig().usage_age_days, null);
console.log("migCreateConfig usage_age_days: PASS");

// source disposition: absent -> "system" (follow the global setting), a chosen
// value travels, and the per-job form offers the same three values
a = api({ vals: { "#mig_parallel": "1", "#mig_bwlimit": "0" } });
assert.strictEqual(a.migCreateConfig().source_disposition, "system");
a = api({ vals: { "#mig_parallel": "1", "#mig_bwlimit": "0", "#mig_source_disposition": "delete" } });
assert.strictEqual(a.migCreateConfig().source_disposition, "delete");
const configForm = extract("migConfigControls");
assert(configForm.includes("c.source_disposition"), "the per-job form must show the job's current value");
console.log("migCreateConfig source_disposition: PASS");
// damaged disk: absent -> "pause" (the job waits for the admin), a chosen value travels
a = api({ vals: { "#mig_parallel": "1", "#mig_bwlimit": "0" } });
assert.strictEqual(a.migCreateConfig().on_damaged, "pause");
a = api({ vals: { "#mig_parallel": "1", "#mig_bwlimit": "0", "#mig_on_damaged": "continue" } });
assert.strictEqual(a.migCreateConfig().on_damaged, "continue");
assert(extract("migConfigControls").includes('"pause", "continue"'), "the per-job form must offer both");
console.log("migCreateConfig on_damaged: PASS");

// The per-job form: "delete" needs verify, and on a live job verify is frozen, so a
// live job whose verify is off must not be offered a disposition the API will refuse.
// Every top-level MIG_* constant and every helper the form calls, lifted from the
// source: naming them one by one means the next branch that adds a label breaks
// THIS test instead of its own.
const migConsts = [...src.matchAll(/^const (MIG_[A-Z_]+) = ([\s\S]*?);\n/gm)]
  .map((m) => `const ${m[1]} = ${m[2]};`)
  .join("\n");
const controls = new Function(
  migConsts + "\n" +
    ["migEscape", "migOpt", "migBytesToGb", "migDaysToValueUnit", "migConfigControls"]
      .map(extract)
      .join("\n") +
    "\nreturn migConfigControls;"
)();
const form = (status, verify) => controls({ id: "m1", status, config: { verify } });
assert(form("pending", false).includes('value="delete"'), "a job that has not started may still choose delete");
assert(!form("running", false).includes('value="delete"'), "a live job with verify off must not be offered delete");
assert(form("running", true).includes('value="delete"'), "a live job with verify on keeps delete");
console.log("migConfigControls source disposition vs frozen verify: PASS");

// load policy: the create POST carries load_policy per the form; default static
a = api({ vals: { "#mig_parallel": "1", "#mig_bwlimit": "0" } });
assert.deepStrictEqual(a.migCreateConfig().load_policy,
  { mode: "static", parallelism_min: 1, parallelism_max: 4, pause_above: 0, baseline_window: 5 },
  "default create load_policy is safe/static");
a = api({ vals: {
  "#mig_parallel": "1", "#mig_bwlimit": "0", "#mig_load_mode": "adaptive",
  "#mig_parallel_min": "2", "#mig_parallel_max": "6", "#mig_pause_above": "40"
} });
assert.deepStrictEqual(a.migCreateConfig().load_policy,
  { mode: "adaptive", parallelism_min: 2, parallelism_max: 6, pause_above: 40, baseline_window: 5 },
  "adaptive load_policy rides the form values into the config");
console.log("migCreateConfig load_policy: PASS");

// migLoadBadge: the row shows effective parallelism + the last decision reason
const badge = new Function(
  extract("migEscape") + "\n" + extract("migLoadBadge") + "\nreturn migLoadBadge;"
)();
assert.strictEqual(badge({ config: { load_policy: { mode: "static" } } }), "", "static shows no badge");
assert.strictEqual(badge({ config: {} }), "", "no load_policy shows no badge");
let b = badge({
  config: { load_policy: { mode: "adaptive" }, parallelism: 2 },
  load_state: { effective_parallelism: 3, last_reason: "idle 3 ticks: parallelism 2 -> 3" }
});
assert(b.includes("p=3"), "effective parallelism is shown on the row");
assert(b.includes("idle 3 ticks"), "the last decision reason is shown on the row");
assert(b.includes("mig-load-parallel") && b.includes("mig-load-reason"), "stable hooks for the e2e");
b = badge({ config: { load_policy: { mode: "adaptive" }, parallelism: 1 }, pause_reason: "load", load_state: {} });
assert(b.includes("label-warning") && b.includes("paused by load"), "a load-paused row is highlighted");
console.log("migLoadBadge: PASS");

// migLoadPolicyKey: an inert static default == an absent policy, so editing
// another field on an old job (no load_policy) sends no load_policy (SM11/SM12).
const lp = new Function(
  extract("migLoadPolicyObj") + "\n" + extract("migLoadPolicyKey") +
    "\nreturn { key: migLoadPolicyKey, obj: migLoadPolicyObj };"
)();
assert.strictEqual(lp.key(null), "none");
assert.strictEqual(
  lp.key({ mode: "static", parallelism_min: 1, parallelism_max: 4, pause_above: 0, baseline_window: 5 }),
  "none", "inert static default is treated as no policy");
assert.strictEqual(
  lp.key(lp.obj("static", "1", "4", "0", 5)), lp.key(undefined),
  "an old job with the form at static-default carries no load_policy");
assert.notStrictEqual(lp.key(lp.obj("adaptive", "1", "4", "0", 5)), "none", "adaptive is a real policy");
assert.notStrictEqual(lp.key(lp.obj("static", "2", "6", "0", 5)), "none", "static with a non-default range is a real value");
console.log("migLoadPolicyKey: PASS");

// Apply sends only what changed, and names the fields that weaken a guarantee
const changes = new Function(
  extract("migConfigChanges") + "\n" + extract("migWeakenedFields") +
    "\nconst MIG_WEAKENING = { min_free_bytes: function (o, n) { return (n || 0) < (o || 0); }, failure_policy: function (o, n) { return o === 'pause' && n !== 'pause'; } };" +
    "\nreturn { migConfigChanges: migConfigChanges, migWeakenedFields: migWeakenedFields };"
)();
const cur = { parallelism: 1, failure_policy: "pause", min_free_bytes: 1e9, verify: true };
assert.deepStrictEqual(changes.migConfigChanges(cur, { parallelism: 2, failure_policy: "pause", min_free_bytes: 1e9, verify: true }), { parallelism: 2 });
assert.deepStrictEqual(changes.migWeakenedFields(cur, { min_free_bytes: 0, failure_policy: "retry_forever", parallelism: 2 }), ["min_free_bytes", "failure_policy"]);
assert.deepStrictEqual(changes.migWeakenedFields(cur, { min_free_bytes: 2e9 }), []);
// a pre-upgrade job predates source_disposition/min_free_pct/etc.; a field absent
// from current is not a change, so editing parallelism must not backfill them
// (else the legacy "park" would silently flip to source_disposition "system").
assert.deepStrictEqual(
  changes.migConfigChanges(cur, { parallelism: 2, source_disposition: "system", min_free_pct: 10, on_damaged: "pause", include_never_used: false, order: "none" }),
  { parallelism: 2 },
  "absent-from-current fields must not be sent on a legacy job");
console.log("migConfigChanges / migWeakenedFields: PASS");

console.log("ALL PASS");

// The exclusion reason comes from the API and lands in a title attribute, so it
// is the one string on this panel an admin does not author.
const summary = extract("migRenderSummary");
assert(summary.includes("excluded_trees"), "the preview must read excluded_trees");
assert(
  /\.attr\("title", migEscape\(/.test(summary),
  "the exclusion reason must reach the title attribute escaped"
);
assert(
  summary.includes("excluded_disks_total"),
  "the preview must show how many disks the exclusions cost"
);
console.log("migRenderSummary excluded trees: PASS");

// --------------------------------------------------------------------------- //
// migDate / migRowOrder — the two date columns + interactive sort
// --------------------------------------------------------------------------- //
const migDate = eval("(" + extract("migDate").replace(/^function migDate/, "function") + ")");
assert.strictEqual(migDate(null), "—", "null date -> em dash");
assert.strictEqual(migDate(undefined), "—", "undefined date -> em dash");
assert.strictEqual(migDate("nope"), "—", "non-numeric date -> em dash");
assert.notStrictEqual(migDate(1789854820), "—", "a real epoch renders a date");
console.log("migDate: PASS");

const migRowOrder = eval("(" + extract("migRowOrder").replace(/^function migRowOrder/, "function") + ")");
assert(migRowOrder(300, 100, "desc") < 0, "desc: newer before older");
assert(migRowOrder(100, 300, "desc") > 0, "desc: older after newer");
assert.strictEqual(migRowOrder(200, 200, "desc"), 0, "equal epochs -> 0");
assert(migRowOrder(100, 300, "asc") < 0, "asc: older before newer");
// a missing timestamp is the smallest value -> sorts last when descending
assert(migRowOrder(null, 100, "desc") > 0, "desc: missing sorts after a real date");
assert(migRowOrder(500, null, "desc") < 0, "desc: real date before missing");
console.log("migRowOrder: PASS");

// --------------------------------------------------------------------------- //
// migPager — the trees/disks pagination math (server-side paging)
// --------------------------------------------------------------------------- //
const migPager = eval("(" + extract("migPager").replace(/^function migPager/, "function") + ")");
let pg = migPager(1, 25, 4400);
assert(pg.includes("Page 1 / 176"), "4400/25 -> 176 pages");
assert(pg.includes("(4400 total)"), "shows the total");
assert(/mig-page-prev[^>]*disabled/.test(pg), "prev disabled on page 1");
assert(!/mig-page-next[^>]*disabled/.test(pg), "next enabled on page 1");
pg = migPager(176, 25, 4400);
assert(/mig-page-next[^>]*disabled/.test(pg), "next disabled on the last page");
assert(migPager(1, 25, 0).includes("Page 1 / 1"), "empty -> a single page");
console.log("migPager: PASS");

// --------------------------------------------------------------------------- //
// migDeleteButton — carries the status + disk count so confirm() can state them
// --------------------------------------------------------------------------- //
const migDeleteButton = new Function(
  extract("migEscape") + "\n" + extract("migDeleteButton") + "\nreturn migDeleteButton;"
)();
const delBtn = migDeleteButton({ id: "mig-x", status: "completed", totals: { items_total: 7 } });
assert(delBtn.includes("mig-delete"), "delete button has the mig-delete hook");
assert(delBtn.includes('data-status="completed"'), "carries the status for confirm");
assert(delBtn.includes('data-items="7"'), "carries the disk count for confirm");
console.log("migDeleteButton: PASS");
