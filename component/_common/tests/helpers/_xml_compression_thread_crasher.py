#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Hammer ``compress_xml``/``decompress_xml`` from many threads at once.

Run as a subprocess, never imported: what it reproduces segfaults the
interpreter, which would take the whole pytest runner with it.

Exit 0 = clean; 1 = a worker raised or a decompress returned the wrong bytes;
a signal status = the crash itself.
"""

import base64
import random
import sys
import threading
from collections import Counter

THREADS = 16
ITERATIONS = 8
PAYLOAD_BYTES = 1_000_000


def _payload():
    # High entropy keeps the frame large, so decompression stays in C with the
    # GIL released long enough for two threads to overlap inside it.
    rnd = random.Random(20260903)
    parts = ["<domain>"]
    size = 0
    while size < PAYLOAD_BYTES:
        serial = "".join(rnd.choice("0123456789abcdef") for _ in range(32))
        fragment = f"<disk dev='vda' bus='virtio' serial='{serial}'/>"
        parts.append(fragment)
        size += len(fragment)
    parts.append("</domain>")
    return "".join(parts)


def main():
    from isardvdi_common.helpers.xml_compression import compress_xml, decompress_xml

    payload = _payload()
    # Unwrap the ``r.binary(...)`` term into the bytes a read from rdb returns.
    frame = base64.b64decode(compress_xml(payload).base64_data)

    failures = []
    barrier = threading.Barrier(THREADS)

    def worker():
        try:
            barrier.wait()
            for _ in range(ITERATIONS):
                compress_xml(payload)
                if decompress_xml(frame) != payload:
                    failures.append("decompress returned the wrong bytes")
        except BaseException as exc:  # noqa: BLE001 — any escape is a finding
            failures.append(repr(exc))

    threads = [threading.Thread(target=worker) for _ in range(THREADS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    if failures:
        print(f"FAILURES n={len(failures)}", file=sys.stderr)
        for text, count in Counter(f[:90] for f in failures).most_common(8):
            print(f"  {count:5d}x {text}", file=sys.stderr)
        return 1
    print("SURVIVED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
