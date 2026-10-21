// SPDX-License-Identifier: AGPL-3.0-or-later
//
// The storage admin decides a row's buttons from the row alone and leaves the
// rest to the API, whose refusals say why. Run by `make ci-test-webapp-js`, or
// `bun <this file>`.

const fs = require("fs");
const assert = require("assert");
const path = require("path");

const src = fs.readFileSync(path.join(__dirname, "..", "storage.js"), "utf8");

function extract (name) {
  const start = src.indexOf("function " + name + " ");
  assert.ok(start !== -1, "could not find function " + name);
  const end = src.indexOf("\n}", start);
  return src.slice(start, end + 2);
}

const names = [
  "storageRegistryAction",
  "storageActionAllowed",
  "storageModalButtonAllowed",
  "storageBatchReport",
  "storageRowActions",
];
const ctx = {};
new Function(
  "ctx",
  names.map(extract).join("\n") + "\n" + names.map(n => `ctx.${n} = ${n};`).join("\n")
)(ctx);

function classes (row) {
  return ctx.storageRowActions(row).join(" ");
}

// --- a row offers what its own status and perms allow ----------------------
const desktop = { id: "leaf", status: "ready", perms: ["r", "w"] };
assert.ok(classes(desktop).includes("btn-sparsify-now"));
assert.ok(classes(desktop).includes("btn-dig-holes-now"));
assert.ok(classes(desktop).includes("btn-check-integrity"));
console.log("a ready writable disk offers its writers: PASS");

const readOnly = { id: "tpl", status: "ready", perms: ["r"] };
assert.ok(!classes(readOnly).includes("btn-dig-holes-now"));
assert.ok(classes(readOnly).includes("btn-sparsify-now"));
console.log("a read-only disk is never offered a dig: PASS");

const busy = { id: "busy", status: "maintenance", perms: ["r", "w"] };
assert.ok(!classes(busy).includes("btn-dig-holes-now"));
assert.ok(!classes(busy).includes("btn-sparsify-now"));
assert.ok(classes(busy).includes("btn-find"));
console.log("a disk not ready offers no writer: PASS");

// --- the listing is not asked for per-row actions --------------------------
assert.ok(classes({ ...desktop, allowed_actions: [] }).includes("btn-dig-holes-now"));
assert.ok(!src.includes("write_lock"));
console.log("rows ignore allowed_actions and no lock is shown: PASS");

// --- the search modal follows what search-info admits ----------------------
const info = { status: "ready", allowed_actions: ["check_integrity", "derive", "find", "sparsify"] };
assert.strictEqual(ctx.storageModalButtonAllowed(info, "btn btn-info btn-xs btn-modal-dig-holes"), false);
assert.strictEqual(ctx.storageModalButtonAllowed(info, "btn btn-info btn-xs btn-modal-sparsify"), true);
assert.strictEqual(ctx.storageModalButtonAllowed(info, "btn btn-info btn-xs btn-modal-create"), true);
assert.strictEqual(ctx.storageModalButtonAllowed({ status: "maintenance" }, "btn-modal-sparsify"), false);
assert.strictEqual(ctx.storageModalButtonAllowed({ status: "maintenance" }, "btn-modal-find"), true);
console.log("the modal follows search-info: PASS");

// --- a bulk dig says per disk why one was left out -------------------------
const report = ctx.storageBatchReport({
  queued: 1,
  results: [
    { storage_id: "a", task_id: "t-a" },
    { storage_id: "b", description_code: "storage_used_by_template", message: "Storage b is a template's disk" },
    { storage_id: "c", description_code: "storage_has_children" },
  ],
});
assert.strictEqual(report.refused, 2);
assert.ok(report.text.startsWith("Queued on 1 of 3 disk(s)."));
assert.ok(report.text.includes("b: Storage b is a template's disk"));
assert.ok(report.text.includes("c: storage_has_children"));
console.log("the bulk report gives a reason per refused disk: PASS");

// --- the bulk dig has no per-status path ------------------------------------
assert.ok(!src.includes("dig-holes/${status}"));
assert.ok(!/if \(status = "/.test(src));
console.log("no per-status dig and no status assignment in a test: PASS");

// --- the row dig verifies only when asked -----------------------------------
assert.ok(src.includes("dig-holes/priority/low?verify=${verify}"));
assert.ok(src.includes('class="dig-holes-verify"'));
console.log("the row dig sends verify from its checkbox: PASS");
