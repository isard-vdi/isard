// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Run by `make ci-test-webapp-js`, or directly with `bun <this file>`.

const fs = require("fs");
const assert = require("assert");
const path = require("path");

const src = fs.readFileSync(path.join(__dirname, "..", "..", "..", "isard.js"), "utf8");
const start = src.indexOf("function hostToUnicode (");
assert.ok(start !== -1, "could not find function hostToUnicode");
const ctx = {};
new Function(
  "ctx",
  "punycode",
  src.slice(start, src.indexOf("\n}", start) + 2) + "\nctx.hostToUnicode = hostToUnicode;"
)(ctx, require("punycode"));

assert.strictEqual(ctx.hostToUnicode("xn--ctedra-ita.cat"), "càtedra.cat");
console.log("an idna ascii host name is shown in unicode: PASS");

assert.strictEqual(ctx.hostToUnicode("acme.org"), "acme.org");
console.log("an ascii host name is shown as it is: PASS");

assert.strictEqual(ctx.hostToUnicode("xn--ü.acme.org"), "xn--ü.acme.org");
console.log("a label that cannot be decoded is shown as it is: PASS");
