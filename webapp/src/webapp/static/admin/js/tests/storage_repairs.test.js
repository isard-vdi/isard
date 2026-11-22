// SPDX-License-Identifier: AGPL-3.0-or-later
//
// The storage admin's repair buttons, the bulk integrity check, and the desktop
// disk problems the desktops admin shows. Run by `make ci-test-webapp-js`, or
// `bun <this file>`.

const fs = require("fs");
const assert = require("assert");
const path = require("path");

function load (file, names, consts = []) {
  const src = fs.readFileSync(path.join(__dirname, "..", file), "utf8");
  const extract = (name) => {
    const start = src.indexOf("function " + name + " ");
    assert.ok(start !== -1, "could not find function " + name);
    return src.slice(start, src.indexOf("\n}", start) + 2);
  };
  const constant = (name) => {
    const match = src.match(new RegExp("^const " + name + " = .*;$", "m"));
    assert.ok(match, "could not find const " + name);
    return match[0];
  };
  const ctx = { src };
  new Function(
    "ctx",
    consts.map(constant).join("\n") + "\n" + names.map(extract).join("\n") + "\n" +
      [...names, ...consts].map(n => `ctx.${n} = ${n};`).join("\n")
  )(ctx);
  return ctx;
}

const storage = load("storage.js", ["storageRowActions", "storageBulkCheckRequest"]);
const classes = (row) => storage.storageRowActions(row).join(" ");

// --- per-row repairs ----------------------------------------------------------
const ready = { id: "s1", status: "ready", perms: ["r", "w"] };
assert.ok(classes(ready).includes("btn-zero-scan-now"));
assert.ok(!classes(ready).includes("btn-repair-leaks"));
assert.ok(classes({ ...ready, pending_actions: { repair_leaks: {} } }).includes("btn-repair-leaks"));
assert.ok(!classes({ ...ready, status: "maintenance" }).includes("btn-zero-scan-now"));
console.log("a ready disk offers a zero scan, and a leak repair when marked: PASS");

const damaged = storage.storageRowActions({ id: "s2", status: "damaged" }).join(" ");
assert.ok(/btn-repair-all" title="Repair all \(costly/.test(damaged), damaged);
assert.ok(/btn-sparsify-now" title="Sparsify disk \(costly\)/.test(classes(ready)));
console.log("the costly repairs say so: PASS");

// --- the bulk check calls the existing per-status endpoint ---------------------
assert.deepStrictEqual(storage.storageBulkCheckRequest("ready"), {
  type: "PUT", url: "/api/v4/admin/items/storage/check/ready"
});
assert.ok(storage.src.includes("#btn-check-integrity-status"));
const page = fs.readFileSync(path.join(__dirname, "..", "..", "..", "..", "templates", "admin", "pages", "storage.html"), "utf8");
assert.ok(page.includes('id="btn-check-integrity-status"'));
assert.ok(page.includes('id="check-integrity-status"'));
console.log("the bulk check button calls the per-status check: PASS");

assert.ok(page.includes('<option value="review_coherence">review_coherence</option>'));
console.log("a disk a check found without file can be listed: PASS");

// --- a batch report stays short at any size and keeps its line breaks ----------
const reports = load("storage.js", ["storageBatchReport", "storageNoticeHtml"]);
const many = { queued: 1, results: [{ storage_id: "ok", task_id: "t" }] };
for (let i = 0; i < 5000; i++) many.results.push({ storage_id: `b${i}`, description_code: "storage_pending_task" });
many.results.push({ storage_id: "<p>", description_code: "storage_has_children", message: "has children" });
const big = reports.storageBatchReport(many);
assert.strictEqual(big.refused, 5001);
assert.strictEqual(
  big.text,
  "Queued on 1 of 5002 disk(s).<br>5000 refused: storage_pending_task (b0, b1, b2, ...)" +
    "<br>1 refused: storage_has_children (&lt;p&gt;): has children"
);
console.log("a batch report groups the refusals by reason, escaped: PASS");

// --- a mass action by status answers the count; its end comes as a notice -------
const later = load("storage.js", ["storageBatchAccepted", "storageAdminNotice", "storageNoticeHtml"]);
const accepted = later.storageBatchAccepted("integrity checks", { status: "ready", accepted: 49388 });
assert.ok(accepted.includes("integrity checks on 49388 ready disk(s)"), accepted);
assert.ok(/notice/.test(accepted), accepted);
assert.ok(storage.src.includes("socket.on('msg'"));
const end = later.storageAdminNotice({
  id: "", title: "Integrity checks of the ready disks", type: "info",
  description: "Queued on 1 of 2 disk(s).\n1 refused: storage_open_not_checkable (s<2>)",
  params: { hide: false }
});
assert.strictEqual(end.text, "Queued on 1 of 2 disk(s).<br>1 refused: storage_open_not_checkable (s&lt;2&gt;)");
assert.strictEqual(end.hide, false);
assert.strictEqual(later.storageAdminNotice({ id: "batch-1", title: "User data generated", description: "1/2", params: {} }), null);
assert.strictEqual(later.storageAdminNotice({ id: "", title: "", description: "", params: { delete: true } }), null);
console.log("the end of a mass action shows its lines, and no other page's notice: PASS");

const evil = '<img src=x onerror=alert(1)>';
const evilAccepted = later.storageBatchAccepted("checks", { status: evil, accepted: evil });
assert.ok(!evilAccepted.includes("<img"), evilAccepted);
assert.ok(evilAccepted.includes("&lt;img src=x onerror=alert(1)&gt;"), evilAccepted);
const evilEnd = later.storageAdminNotice({ id: "", title: evil, description: evil, type: "info", params: {} });
assert.strictEqual(evilEnd.title, "&lt;img src=x onerror=alert(1)&gt;");
assert.strictEqual(evilEnd.text, "&lt;img src=x onerror=alert(1)&gt;");
assert.strictEqual(evilEnd.title_escape, false);
console.log("a status, count or title carrying markup reaches the notice escaped: PASS");

// --- the allowed list is edited with the shared allowed modal -------------------
const sweep = fs.readFileSync(path.join(__dirname, "..", "storage_sweep_config.js"), "utf8");
assert.ok(sweep.includes('modalAllowedsFormShow("storage_repair"'));
console.log("the costly repair list opens the allowed editor: PASS");

// --- the desktops admin lists the problems and what the quick fixes did --------
globalThis.escapeHtmlText = load("../../isard.js", ["escapeHtmlText"]).escapeHtmlText;
const desktops = load(
  "desktops.js",
  ["formatFixEta", "storageProblemLine", "storageQuickFixLine", "storageProblemLines"],
  ["STORAGE_START_CODES"]
);
const report = {
  quick_fixes: [
    { storage_id: "s1", fix: "repair_leaks", task_id: "t1" },
    { storage_id: "s1", fix: "check", recorded: "check_integrity" },
  ],
  disks: [{
    storage_id: "s1",
    problems: [
      { code: "storage_leaks", fix: "repair_leaks", mode: "quick", allowed: true },
      { code: "storage_zeros", fix: "dig_holes", mode: "costly", allowed: false },
      { code: "storage_review_damage", fix: null, mode: "admin", allowed: false },
    ],
  }],
};
const lines = desktops.storageProblemLines("d1", report);
assert.strictEqual(lines.length, 5);
assert.ok(lines[0].includes("Queued repair_leaks on s1"), lines[0]);
assert.ok(lines[1].includes("left for the storage sweep"), lines[1]);
assert.ok(lines[2].includes('data-fix="repair_leaks"'), lines[2]);
assert.ok(lines[3].includes("not allowed") && !lines[3].includes("btn-storage-fix"), lines[3]);
assert.ok(lines[4].includes("needs an administrator"), lines[4]);
const allowedCostly = desktops.storageProblemLine("d1", { storage_id: "s1" },
  { code: "storage_zeros", fix: "dig_holes", mode: "costly", allowed: true });
assert.ok(allowedCostly.includes('data-fix="dig_holes"') && allowedCostly.includes("btn-danger"));
const waiting = desktops.storageProblemLine("d1", { storage_id: "s1", task: { position: 3, eta_seconds: 45 } },
  { code: "storage_busy", fix: null, mode: "wait" });
assert.ok(waiting.includes("queued #3, ETA ~45 s"), waiting);
assert.ok(desktops.STORAGE_START_CODES.includes("desktop_storage_not_ready"));
console.log("the desktop disk problems show the quick fixes and who may run the rest: PASS");
