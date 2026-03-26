#!/usr/bin/env bash
# Download the latest NVIDIA PCI device IDs from the upstream pci.ids database
# and update the bundled nvidia_pci_ids.txt used by gpu_discovery.py.
#
# Usage: ./update_nvidia_pci_ids.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OUTPUT="$SCRIPT_DIR/src/lib/nvidia_pci_ids.txt"
URL="https://pci-ids.ucw.cz/v2.2/pci.ids.gz"

echo "Downloading pci.ids.gz from $URL ..."
curl -sL "$URL" \
  | gunzip \
  | python3 -c "
import sys, re
in_nvidia = False
for line in sys.stdin:
    line = line.rstrip('\n')
    if not line.strip() or line.startswith('#'):
        continue
    if re.match(r'^[0-9a-fA-F]{4}\s', line):
        in_nvidia = line.lower().startswith('10de')
        continue
    if in_nvidia and line.startswith('\t') and not line.startswith('\t\t'):
        m = re.match(r'^\t([0-9a-fA-F]{4})\s+(.+)', line)
        if m:
            print(f'{m.group(1)}  {m.group(2).strip()}')
" > "$OUTPUT"

count=$(wc -l < "$OUTPUT")
echo "Written $count NVIDIA PCI IDs to $OUTPUT"
