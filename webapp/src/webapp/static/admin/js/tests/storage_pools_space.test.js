// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Functional tests for the storage-pool Space cell. Run by
// `make ci-test-webapp-js`, or directly with `bun <this file>`.
//
// What matters here is what the cell REFUSES to say. On a thin pool the
// filesystem free space is the pool's logical size, so an admin reading it
// would plan against a number that was 5x to 17x optimistic in the field. The
// cell must therefore never present a filesystem figure as the pool's space,
// and must be explicit when nobody has measured it.

const fs = require("fs");
const assert = require("assert");
const path = require("path");

const SRC = path.join(__dirname, "..", "storage_pools.js");
const src = fs.readFileSync(SRC, "utf8");

function extract (name) {
  // Grab a top-level `function name (...) { ... }` up to its column-0 closing brace.
  const start = src.indexOf("function " + name);
  assert.ok(start !== -1, "could not find function " + name);
  const end = src.indexOf("\n}", start);
  assert.ok(end !== -1, "could not find the end of " + name);
  return src.slice(start, end + 2);
}

const ctx = {};
new Function("ctx", extract("spHumanBytes") + "\nctx.spHumanBytes = spHumanBytes;")(ctx);
new Function("ctx", extract("spEsc") + "\nctx.spEsc = spEsc;")(ctx);
new Function(
  "ctx", "spHumanBytes", "spEsc", "SP_USAGE_MAX_AGE_S",
  extract("spSpaceCell") + "\nctx.spSpaceCell = spSpaceCell;"
)(ctx, ctx.spHumanBytes, ctx.spEsc, 900);

const { spSpaceCell } = ctx;
const NOW = 1786790000;
const TiB = 1024 ** 4;

// --- nobody publishes: say so, do not fall back to anything -----------------
{
  const html = spSpaceCell(null, NOW);
  assert.ok(html.includes("not reported"), "must say it is not reported");
  assert.ok(html.includes("STORAGE_POOL_VDO_STATS"), "must say how to fix it");
}

// --- a network pool cannot be measured here ---------------------------------
{
  const html = spSpaceCell({ kind: "network", reason: "served by another host" }, NOW);
  assert.ok(html.includes("network"), "must name the case");
  assert.ok(!html.includes("free"), "must not present any free-space figure");
}

// --- thin with a real measurement: physical shown, filesystem only in the tip
{
  const html = spSpaceCell({
    kind: "local-thin", physical_total_bytes: 16.94 * TiB,
    physical_free_bytes: 16.83 * TiB, filesystem_free_bytes: 83.09 * TiB,
    measured_at: NOW - 30, node: "storage-1", source: "dm-status"
  }, NOW);
  assert.ok(html.includes("16.8 TB free"), "shows the PHYSICAL free space");
  assert.ok(html.includes("thin"), "flags the pool as thin");
  assert.ok(html.includes("LOGICAL size and not the constraint"),
    "explains the filesystem claim instead of showing it as the space");
  assert.ok(!/>\s*83\.1 TB free/.test(html), "the filesystem lie must not be the headline");
}

// --- thin without the fill: capacity is free to read, the fill is not --------
{
  const html = spSpaceCell({
    kind: "local-thin", physical_total_bytes: 16.94 * TiB,
    physical_free_bytes: null, filesystem_free_bytes: 83.09 * TiB,
    reason: "needs the device-mapper ioctl", measured_at: NOW
  }, NOW);
  assert.ok(html.includes("? of 16.9 TB"), "shows capacity but not an invented fill");
  assert.ok(html.includes("fa-warning"), "warns rather than looking measured");
}

// --- thick: the filesystem figure IS the physical one -----------------------
{
  const html = spSpaceCell({
    kind: "local-thick", physical_total_bytes: 10 * TiB,
    physical_free_bytes: 9.81 * TiB, filesystem_free_bytes: 9.81 * TiB,
    measured_at: NOW - 5, node: "storage-1", source: "statvfs"
  }, NOW);
  assert.ok(html.includes("9.8 TB free"));
  assert.ok(!html.includes("thin"), "must not be flagged thin");
}

// --- stale measurement is marked, not silently trusted ----------------------
{
  const html = spSpaceCell({
    kind: "local-thin", physical_total_bytes: 16.94 * TiB,
    physical_free_bytes: 16.83 * TiB, measured_at: NOW - 4000,
    node: "storage-1", source: "dm-status"
  }, NOW);
  assert.ok(html.includes("fa-clock-o"), "stale measurements must be visible as stale");
}

// --- a hostile reason string cannot break out of the title attribute --------
{
  const html = spSpaceCell({ kind: "unknown", reason: '"><img src=x onerror=alert(1)>' }, NOW);
  assert.ok(!html.includes("<img"), "reason must be escaped into the attribute");
}

// --- a pool spread over several devices -------------------------------------
{
  const GiB = 1024 ** 3;
  const devices = [
    { path: "/isard/storage_pools/p/media", usages: ["media"],
      physical_total_bytes: 200 * GiB, physical_free_bytes: 3 * GiB },
    { path: "/isard/storage_pools/p", usages: ["pool", "groups", "templates"],
      physical_total_bytes: 4000 * GiB, physical_free_bytes: 3000 * GiB }
  ];
  const html = spSpaceCell({
    kind: "local-thick", path: devices[0].path, usages: devices[0].usages,
    physical_total_bytes: devices[0].physical_total_bytes,
    physical_free_bytes: devices[0].physical_free_bytes,
    measured_at: NOW - 5, node: "storage-1", source: "statvfs"
  }, NOW, devices);

  assert.ok(html.includes("3.0 GB free"), "leads with the constraining device");
  assert.ok(!/>\s*2\.9 TB free/.test(html), "the roomy device must not be the headline");
  assert.ok(html.includes("of 2 devs"), "says the figure is one of several");
  assert.ok(html.includes("spans 2 devices"), "the tooltip explains the spread");
  assert.ok(html.includes("/isard/storage_pools/p/media"), "names the constraint");
  assert.ok(html.includes("/isard/storage_pools/p ("), "names the other device too");
}

// --- one device: nothing about the cell may change --------------------------
{
  const usage = {
    kind: "local-thick", physical_total_bytes: 10 * TiB,
    physical_free_bytes: 9.81 * TiB, measured_at: NOW - 5,
    node: "storage-1", source: "statvfs"
  };
  const alone = spSpaceCell(usage, NOW);
  const withOne = spSpaceCell(usage, NOW, [Object.assign({ path: "/isard", usages: ["pool"] }, usage)]);
  assert.strictEqual(withOne, alone, "a one-device pool must render exactly as before");
  assert.ok(!withOne.includes("devs"), "and must not mention a spread it does not have");
}

// --- not reported: say WHICH problem it is ----------------------------------
{
  const why = "This pool has no mountpoint, so there is nothing to measure.";
  const html = spSpaceCell(null, NOW, null, why);
  assert.ok(html.includes("not reported"), "still says it is not reported");
  assert.ok(html.includes("no mountpoint"), "carries the reason the API gave");
  assert.ok(!html.includes("STORAGE_POOL_VDO_STATS"),
    "must not send this admin to configure a node that was never the problem");
}

// --- and keeps the old wording when the API says nothing --------------------
{
  const html = spSpaceCell(null, NOW, null, null);
  assert.ok(html.includes("STORAGE_POOL_VDO_STATS"), "falls back to the generic advice");
}

// --- a hostile reason cannot break out of the title attribute either --------
{
  const html = spSpaceCell(null, NOW, null, '"><img src=x onerror=alert(1)>');
  assert.ok(!html.includes("<img"), "the API-supplied reason must be escaped too");
}

console.log("storage_pools_space.test.js: all assertions passed");
