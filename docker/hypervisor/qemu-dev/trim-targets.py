#!/usr/bin/env python3
"""Trim Alpine's qemu APKBUILD to the packages this image installs."""

import re
import sys

APKBUILD = "APKBUILD"
lines = open(APKBUILD).read().split("\n")
changed = []

# Drop every subpackage this image does not install. Leaving one declared while
# its content is no longer built is a hard abuild failure ("Missing subpkgdir for
# qemu-doc"), which is what --disable-docs would otherwise cause. The two that
# survive are appended further down by the APKBUILD itself (qemu-modules and
# qemu-img), plus qemu-system-x86_64 from the _subsystems loop.
out, done = [], False
i = 0
while i < len(lines):
    if lines[i] == 'subpackages="' and not done:
        out.append('subpackages="')
        i += 1
        while i < len(lines) and lines[i].strip() != '"':
            i += 1
        out.append('\t"')
        i += 1
        done = True
        continue
    out.append(lines[i])
    i += 1
if not done:
    sys.exit("trim-targets: the opening 'subpackages=\"' block was not found")
lines = out
changed.append("subpackages -> only img, modules and system-x86_64")

# The `case "$CARCH"` blocks above append more architectures to _subsystems, so
# overriding the list at its declaration is not enough — do it immediately
# before the loop that turns it into subpackages.
out, done = [], False
for line in lines:
    if line.startswith("for _sub in $_subsystems; do"):
        out.append('_subsystems="system-x86_64"')
        done = True
    out.append(line)
if not done:
    sys.exit("trim-targets: 'for _sub in $_subsystems; do' not found")
lines = out
changed.append("_subsystems -> system-x86_64")

# One target per compile pass instead of every target qemu can emulate.
wanted = {
    "--enable-linux-user": "--target-list=x86_64-linux-user",
    "--disable-linux-user": "--target-list=x86_64-softmmu",
}
out, seen = [], set()
for line in lines:
    out.append(line)
    stripped = line.strip()
    for flag, target in wanted.items():
        if stripped == flag + " \\":
            indent = line[: len(line) - len(line.lstrip())]
            out.append(f"{indent}{target} \\")
            seen.add(flag)
            changed.append(f"{flag} -> {target}")
lines = out
missing = set(wanted) - seen
if missing:
    sys.exit(f"trim-targets: configure flags not found: {sorted(missing)}")

# The qemu manuals are not shipped in this image.
lines = [line.replace("--enable-docs", "--disable-docs") for line in lines]
changed.append("--enable-docs -> --disable-docs")

text = "\n".join(lines)

# qemu's own test suite is upstream's and Alpine's job, not this image's.
options = re.search(r'^options="([^"]*)"', text, re.M)
if options:
    if "!check" not in options.group(1):
        text = (
            text[: options.start()]
            + f'options="{options.group(1)} !check"'
            + text[options.end() :]
        )
        changed.append("!check appended to options")
else:
    text = text.replace("\nbuild()", '\noptions="!check"\n\nbuild()', 1)
    changed.append('options="!check" added')

open(APKBUILD, "w").write(text)
for entry in changed:
    print("trim-targets:", entry)
