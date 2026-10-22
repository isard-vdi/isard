// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Tests for the admin job scheduler page. Run by `make ci-test-webapp-js`,
// or directly with `bun <this file>`.

const fs = require("fs");
const assert = require("assert");
const path = require("path");

const SRC = path.join(__dirname, "..", "schedulers.js");
const src = fs.readFileSync(SRC, "utf8");
const MODALS = path.join(
  __dirname, "..", "..", "..", "..", "templates", "admin", "pages", "schedulers_modals.html"
);
const modals = fs.readFileSync(MODALS, "utf8");

function extract (name) {
  const start = src.indexOf("\nfunction " + name + "(");
  assert.ok(start !== -1, "could not find function " + name);
  const end = src.indexOf("\n}", start + 1);
  assert.ok(end !== -1, "could not find the end of " + name);
  return src.slice(start, end + 2);
}

function extractVar (name) {
  const start = src.indexOf("\nvar " + name + " =");
  assert.ok(start !== -1, "could not find var " + name);
  const end = src.indexOf("];", start);
  return src.slice(start, end + 2);
}

const ctx = {};
new Function(
  "ctx",
  extractVar("SCHEDULER_HIDDEN_ACTIONS") +
    extract("schedulerVisibleActions") +
    extract("schedulerShowsJob") +
    extract("schedulerDeleteText") +
    "\nctx.schedulerVisibleActions = schedulerVisibleActions;" +
    "\nctx.schedulerShowsJob = schedulerShowsJob;" +
    "\nctx.schedulerDeleteText = schedulerDeleteText;"
)(ctx);

// --- the action filter really removes the recycle bin actions --------------
{
  const actions = [
    { id: "recycle_bin_old_entries_action_delete", name: "x" },
    { id: "recycle_bin_delete_admin", name: "x" },
    { id: "stop_shutting_down_desktops", name: "x" },
  ];
  const ids = ctx.schedulerVisibleActions(actions).map((a) => a.id);
  assert.deepStrictEqual(ids, ["stop_shutting_down_desktops"]);
  assert.ok(!src.includes("old_enties"), "the misspelt action id filters nothing");
}

// --- only system jobs reach the system table from the socket ---------------
{
  assert.strictEqual(ctx.schedulerShowsJob({ id: "a", type: "system" }), true);
  assert.strictEqual(ctx.schedulerShowsJob({ id: "b", type: "bookings" }), false);
  assert.strictEqual(ctx.schedulerShowsJob({ id: "c" }), false);
  assert.strictEqual(ctx.schedulerShowsJob(null), false);
  const handlers = src.slice(src.indexOf("function socketio_on"));
  for (const ev of ["scheduler_jobs_add", "scheduler_jobs_update"]) {
    const body = handlers.slice(handlers.indexOf(ev), handlers.indexOf("});", handlers.indexOf(ev)));
    assert.ok(body.includes("schedulerShowsJob("), ev + " must filter by job type");
  }
}

// --- the delete confirmation names the job, not its next run ---------------
{
  const text = ctx.schedulerDeleteText({ name: "send unused items", next_run_time: 1 });
  assert.ok(text.includes("send unused items"));
  assert.ok(!src.includes("delete scheduled task \" + moment"), "must not show the date");
}

// --- opening the modal twice neither duplicates options nor handlers -------
{
  assert.strictEqual(src.split("function scheduler_init(").length - 1, 1,
    "scheduler_init must be defined once");
  const init = extract("scheduler_init");
  assert.ok(!init.includes(".on("), "scheduler_init must not bind handlers");
  assert.ok(/#action option\[value!=''\]"\)\.remove\(\)/.test(init),
    "scheduler_init must drop the options of the previous opening");
  const ready = src.slice(0, src.indexOf("function socketio_on"));
  assert.ok(ready.includes("scheduler_bind_modal();"), "handlers are bound once, on load");
}

// --- the modal calls no function the page does not use ---------------------
{
  assert.ok(!modals.includes("hiddenFields"), "dead hiddenFields handler");
}

console.log("schedulers.test.js: all assertions passed");
