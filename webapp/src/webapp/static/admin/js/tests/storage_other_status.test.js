// SPDX-License-Identifier: AGPL-3.0-or-later
//
// The "other status" panel owns its status: the ready panel, the duplicated
// UUID panel and an empty selection never leak into it. Run by
// `make ci-test-webapp-js`, or `bun <this file>`.

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

function handler (selector) {
  const start = src.indexOf("$('" + selector + "').on('change'");
  assert.ok(start !== -1, "could not find the change handler of " + selector);
  const end = src.indexOf("\n  });", start);
  return src.slice(start, end);
}

const names = ["storageOtherStatus", "storageGlobalActionUrl"];
const ctx = {};
new Function(
  "ctx",
  names.map(extract).join("\n") + "\n" + names.map(n => `ctx.${n} = ${n};`).join("\n")
)(ctx);

// --- no status selected is no status ----------------------------------------
assert.strictEqual(ctx.storageOtherStatus("none"), null);
assert.strictEqual(ctx.storageOtherStatus(""), null);
assert.strictEqual(ctx.storageOtherStatus(undefined), null);
assert.strictEqual(ctx.storageOtherStatus("orphan"), "orphan");
console.log("the placeholder option selects no status: PASS");

assert.strictEqual(ctx.storageGlobalActionUrl("find", "none"), null);
assert.strictEqual(ctx.storageGlobalActionUrl("find", ""), null);
assert.strictEqual(ctx.storageGlobalActionUrl("find", "orphan"), "/api/v4/items/storage/find/orphan");
assert.strictEqual(ctx.storageGlobalActionUrl("find", "a b"), "/api/v4/items/storage/find/a%20b");
console.log("a whole-table action never targets an empty status: PASS");

// --- picking a status touches only the other-status panel -------------------
const statusChange = handler("#status");
assert.ok(!/\$\(["']\.mactionsStorage["']\)\.attr\(/.test(statusChange));
assert.ok(statusChange.includes(`.mactionsStorage[selectedTableId="storagesOtherTable"]`));
console.log("the ready panel's actions keep their own status: PASS");

const nonePos = statusChange.indexOf("if (!otherTableStatus)");
const createPos = statusChange.indexOf("createDatatable(");
assert.ok(nonePos !== -1 && nonePos < createPos);
console.log("'Select status' empties the table without calling the API: PASS");

// --- the duplicated UUID panel keeps its selection to itself ----------------
const uuidChange = handler("#uuid_status");
assert.ok(!/(^|[^.\w])(newStatus|otherTableStatus)\s*=/.test(uuidChange));
assert.ok(!/\bnewStatus\b/.test(src));
console.log("the duplicated UUID panel does not overwrite the other-status selection: PASS");

// --- a global action refreshes the table it came from -----------------------
const actions = handler(".mactionsStorage");
assert.ok(!actions.includes("storage_ready.ajax.reload"));
assert.ok(actions.includes("$(tableId).DataTable().ajax.reload"));
assert.ok(actions.indexOf("isDataTable(tableId)") < actions.indexOf(".DataTable().search()"));
console.log("a global action reloads its own table and needs one: PASS");

// --- a refused orphan delete shows the API's reason -------------------------
assert.ok(!src.includes("xhr.response.description"));
console.log("the orphan delete error reads responseJSON: PASS");
