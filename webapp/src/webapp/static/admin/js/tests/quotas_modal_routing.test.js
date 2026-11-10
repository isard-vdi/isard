// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Expanding a category or a group row rebinds #modalEditQuota #send, so a
// category-quota save must route by the kind the open handler stored on the
// modal, not a route hardcoded in whichever quota script bound #send last.

const fs = require("fs");
const assert = require("assert");
const path = require("path");

const read = (name) =>
  fs.readFileSync(path.join(__dirname, "..", name), "utf8");
const cat = read("categories_quotas_limits.js");
const grp = read("groups_quotas_limits.js");
const modalTpl = fs.readFileSync(
  path.join(
    __dirname,
    "..",
    "..",
    "..",
    "..",
    "templates",
    "admin",
    "pages",
    "users_modals_quotas_limits.html",
  ),
  "utf8",
);

for (const [name, src] of [
  ["categories", cat],
  ["groups", grp],
]) {
  assert.ok(
    src.includes("$('#modalEditQuota .kind')") && /var\s+quotaKind/.test(src),
    name + " quota save must read the modal kind",
  );
  assert.ok(
    /quota\/"\+\(quotaKind===/.test(src),
    name + " quota PUT url must be built from quotaKind",
  );
  assert.ok(
    !src.includes('quota/category/"+pk') && !src.includes('quota/group/"+pk'),
    name + " must not hardcode a single quota route",
  );
}

assert.ok(
  cat.includes("$('#modalEditQuota .kind').html('category')"),
  "category open must mark the modal kind",
);
assert.ok(
  grp.includes("$('#modalEditQuota .kind').html('group')"),
  "group open must mark the modal kind",
);
assert.ok(
  modalTpl.includes('id="modalEditQuota"') &&
    modalTpl.includes('class="kind"'),
  "the quota modal must render a .kind marker",
);

console.log("quotas_modal_routing.test.js: all assertions passed");
