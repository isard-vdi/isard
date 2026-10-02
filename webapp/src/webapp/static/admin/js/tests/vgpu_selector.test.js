// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Run by `make ci-test-webapp-js`, or directly with `bun <this file>`.

const fs = require("fs");
const assert = require("assert");
const path = require("path");

const SRC = path.join(__dirname, "..", "..", "..", "js", "snippets", "domain_hardware.js");
const src = fs.readFileSync(SRC, "utf8");

function extract (name) {
  const start = src.indexOf("function " + name + "(");
  assert.ok(start !== -1, "could not find function " + name);
  const end = src.indexOf("\n}", start);
  assert.ok(end !== -1, "could not find the end of " + name);
  return src.slice(start, end + 2);
}

const ctx = {};
new Function("ctx", extract("groupVgpuOptions") + "\nctx.groupVgpuOptions = groupVgpuOptions;")(ctx);
new Function("ctx", extract("selectedVgpuIds") + "\nctx.selectedVgpuIds = selectedVgpuIds;")(ctx);
const { groupVgpuOptions, selectedVgpuIds } = ctx;

function profile (id, hypervisors, numa) {
  return {
    id, name: id, description: "desc " + id,
    hypervisors, numa_by_hypervisor: numa || {},
  };
}

function ids (layout) {
  const out = [];
  layout.groups.forEach((g) => g.options.forEach((o) => out.push(o.value.id)));
  layout.ungrouped.forEach((v) => out.push(v.id));
  return out;
}

const NO_GPU = { id: "None", name: "No GPU", description: "None" };

// --- a profile on three hypervisors is listed once, under the first ---------
{
  const layout = groupVgpuOptions([
    NO_GPU,
    profile("NVIDIA-A10-2Q", ["hyp-c", "hyp-a", "hyp-b"]),
  ]);
  assert.deepStrictEqual(ids(layout), ["NVIDIA-A10-2Q", "None"], "each reservable exactly once");
  assert.strictEqual(layout.groups.length, 1);
  assert.strictEqual(layout.groups[0].label, "hyp-a");
  const label = layout.groups[0].options[0].label;
  assert.ok(label.includes("also on hyp-b, hyp-c"), "names the other hypervisors: " + label);
}

// --- profiles still group by hypervisor, none of them repeated --------------
{
  const layout = groupVgpuOptions([
    profile("A10-2Q", ["hyp-a", "hyp-b"]),
    profile("A10-4Q", ["hyp-b"]),
    profile("A16-1Q", ["hyp-c"]),
  ]);
  assert.deepStrictEqual(layout.groups.map((g) => g.label), ["hyp-a", "hyp-b", "hyp-c"]);
  assert.deepStrictEqual(layout.groups.map((g) => g.options.map((o) => o.value.id)),
    [["A10-2Q"], ["A10-4Q"], ["A16-1Q"]]);
  const all = ids(layout);
  assert.strictEqual(new Set(all).size, all.length, "no id listed twice");
  assert.ok(!layout.groups[1].options[0].label.includes("also on"), "single-host profile has no note");
}

// --- a multi-socket server is split by NUMA socket ---------------------------
{
  const layout = groupVgpuOptions([
    profile("pt~n0", ["hyp-a"], { "hyp-a": [0] }),
    profile("pt~n1", ["hyp-a"], { "hyp-a": [1] }),
    profile("8Q", ["hyp-a", "hyp-b"], { "hyp-a": [0, 1], "hyp-b": [0] }),
  ]);
  assert.deepStrictEqual(layout.groups.map((g) => g.label), ["hyp-a · NUMA 0", "hyp-a · NUMA 1"]);
  assert.deepStrictEqual(layout.groups[0].options.map((o) => o.value.id), ["pt~n0", "8Q"]);
  const eightQ = layout.groups[0].options[1].label;
  assert.ok(eightQ.includes("(NUMA 0/1)"), "other sockets noted: " + eightQ);
  assert.ok(eightQ.includes("also on hyp-b"), "other hypervisors noted: " + eightQ);
  const all = ids(layout);
  assert.strictEqual(new Set(all).size, all.length, "no id listed twice across sockets or hosts");
}

// --- a single-socket server stays one plain group ----------------------------
{
  const layout = groupVgpuOptions([
    profile("A", ["hyp-a"], { "hyp-a": [0] }),
    profile("B", ["hyp-a"], { "hyp-a": [0] }),
  ]);
  assert.deepStrictEqual(layout.groups.map((g) => g.label), ["hyp-a"]);
}

// --- profiles without hypervisor data are left ungrouped ---------------------
{
  const layout = groupVgpuOptions([NO_GPU, profile("X", [])]);
  assert.deepStrictEqual(layout.groups, []);
  assert.deepStrictEqual(layout.ungrouped.map((v) => v.id), ["None", "X"]);
  assert.deepStrictEqual(ids(groupVgpuOptions(undefined)), []);
}

// --- the value sent never repeats an id --------------------------------------
{
  assert.deepStrictEqual(
    selectedVgpuIds(["NVIDIA-A10-2Q", "NVIDIA-A10-2Q", "NVIDIA-A10-2Q"]),
    ["NVIDIA-A10-2Q"],
  );
  assert.deepStrictEqual(selectedVgpuIds(["a", "b", "a"]), ["a", "b"]);
  assert.deepStrictEqual(selectedVgpuIds(["None", "a"]), ["a"], "a real profile drops No GPU");
  assert.deepStrictEqual(selectedVgpuIds(["None"]), ["None"]);
  assert.deepStrictEqual(selectedVgpuIds(null), []);
  assert.deepStrictEqual(selectedVgpuIds([]), []);
}

console.log("vgpu_selector: all assertions passed");
