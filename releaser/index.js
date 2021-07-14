#!/usr/bin/env node

const fs = require("fs");
const marked = require("marked");
const git = require("isomorphic-git");
const execSync = require("child_process").execSync;
const quote = require("shell-quote").quote;
const https = require("https");
const semver = require("semver");

if (process.argv.length < 3) {
  console.error("Please, pass the CHANGELOG.md path as argument");
  process.exit(1);
}

let release = false;
if (process.argv.length === 4 && process.argv[3] === "--release") {
  release = true;
}

const changelogPath = process.argv[2];

(async () => {
  try {
    const changelog = fs.readFileSync(changelogPath, "utf8");

    const content = marked.lexer(changelog);

    let latestVersion = false;
    let version;
    let versionTitle;
    let versionChangelog = "";
    for (let i = 0; i < content.length; i++) {
      const item = content[i];

      // Every item in the CHANGELOG with depth 2 is a release
      if (item.type === "heading" && item.depth === 2) {
        if (latestVersion) {
          break;
        }

        latestVersion = true;

        // Get the version number
        version = item.text.match(/\[(.*)\]/).pop();
        versionTitle = item.text;
      }

      if (latestVersion) {
        versionChangelog += item.raw;
      }
    }

    const tagName = "v" + version;

    const getReleases = new Promise((resolve, reject) => {
      https.get(
        `https://gitlab.com/api/v4/projects/${process.env.CI_PROJECT_ID}/releases`,
        (rsp) => {
          let data = [];

          rsp.on("data", (fragment) => {
            data.push(fragment);
          });

          rsp.on("end", () => {
            const body = Buffer.concat(data).toString();

            if (rsp.statusCode !== 200) {
              reject(`HTTP Code ${rsp.statusCode}: ${body}`);
            }

            resolve(body);
          });

          rsp.on("error", (err) => {
            reject(err);
          });
        }
      );
    });

    const releases = JSON.parse(await getReleases);
    if (releases.length > 0) {
      if (semver.lte(tagName, releases[0].tag_name)) {
        console.error(
          "CHANGELOG not updated or outdated! Write an entry to the CHANGELOG >:(!"
        );
        process.exit(1);
      }
    }

    if (release) {
      await git.annotatedTag({
        fs,
        dir: ".",
        ref: tagName,
        message: versionChangelog,
        tagger: {
          name: process.env.GITLAB_USER_NAME,
          email: process.env.GITLAB_USER_EMAIL,
        },
      });

      await git.push({
        fs,
        http: require("isomorphic-git/http/node"),
        dir: ".",
        ref: tagName,
      });

      execSync(
        quote([
          "release-cli",
          "create",
          "--tag-name",
          tagName,
          "--name",
          versionTitle,
          "--description",
          versionChangelog,
        ])
      );
    }
  } catch (err) {
    console.log(err);
    process.exit(1);
  }
})();
