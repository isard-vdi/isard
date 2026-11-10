// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Tests for the admin categories page. Run by `make ci-test-webapp-js`, or
// directly with `bun <this file>`.

const fs = require("fs");
const assert = require("assert");
const path = require("path");

const src = fs.readFileSync(
  path.join(__dirname, "..", "categories_management.js"),
  "utf8"
);
const tpl = (...parts) =>
  fs.readFileSync(
    path.join(__dirname, "..", "..", "..", "..", "templates", ...parts),
    "utf8"
  );
const bastionModal = tpl("admin", "pages", "users_modals_management.html");
const quotasTpl = tpl("admin", "pages", "categories_detail_quotas_limits.html");

// P12: a repeated element id is invalid HTML (jQuery updates only the first),
// so the bastion-domain DNS-hint spans share a class the JS targets.
assert.strictEqual(
  (bastionModal.match(/id="domain-name"/g) || []).length,
  0,
  "bastion modal must not repeat id=domain-name"
);
assert.ok(
  bastionModal.includes('class="bastion-domain-name"'),
  "bastion domain spans must carry the bastion-domain-name class"
);
assert.ok(
  src.includes(".bastion-domain-name") && !src.includes("#domain-name"),
  "JS must target the bastion-domain-name class, not the removed id"
);

// P12: the quotas button class the JS shows/hides for non-editable categories
// must be the one the template actually renders, or the button stays editable.
const quotasClass = src.match(/\.template-detail-categories \.(btn-edit-[a-z-]*quotas)/);
assert.ok(quotasClass, "categories JS must toggle a quotas button class");
assert.ok(
  quotasTpl.includes(quotasClass[1]),
  "the quotas button class the JS toggles (" +
    quotasClass[1] +
    ") must exist in the quotas template"
);

// P12: the dead #allowed_domain population (no such form field) is gone.
assert.ok(
  !src.includes("#allowed_domain"),
  "dead #allowed_domain reference must be removed"
);

// P9: bastion domain verification must honour the config flag; the old
// `|| true` forced it on even when verification was disabled.
assert.ok(
  !src.includes("domain_verification_required || true"),
  "verificationRequired must not be forced true with || true"
);
assert.ok(
  src.includes("domain_verification_required ?? true"),
  "verificationRequired must fall back to true only when the flag is absent"
);

console.log("categories_management.test.js: all assertions passed");
