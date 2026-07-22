# SPDX-License-Identifier: AGPL-3.0-or-later

"""Render the audit results as Markdown + CSV."""

from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass
from io import StringIO

from .error_classifier import ErrorSignature


@dataclass
class Result:
    method: str
    path: str
    status: int
    signature: ErrorSignature | None  # None on 2xx
    body_excerpt: str
    payload_source: str  # "openapi" or "override"


def to_markdown(results: list[Result]) -> str:
    by_status: dict[str, list[Result]] = defaultdict(list)
    for r in results:
        if 200 <= r.status < 300:
            by_status["2xx"].append(r)
        elif 400 <= r.status < 500:
            by_status[f"4xx ({r.status})"].append(r)
        elif r.status >= 500:
            by_status[f"5xx ({r.status})"].append(r)
        else:
            by_status[str(r.status)].append(r)

    out = StringIO()
    out.write("# APIv4 audit report\n\n")
    out.write(f"Total endpoints probed: **{len(results)}**\n\n")
    out.write("## Status summary\n\n")
    for k in sorted(by_status):
        out.write(f"- **{k}**: {len(by_status[k])}\n")
    out.write("\n")

    # Group failures by bucket signature
    buckets: dict[str, list[Result]] = defaultdict(list)
    for r in results:
        if r.signature and r.status >= 400:
            buckets[r.signature.bucket_key()].append(r)

    if buckets:
        out.write("## Failures by signature\n\n")
        # Sort by bucket size descending — biggest buckets first
        for bucket, rs in sorted(buckets.items(), key=lambda t: -len(t[1])):
            out.write(f"### {bucket}  ({len(rs)} hits)\n\n")
            for r in rs[:20]:
                out.write(f"- `{r.method} {r.path}` → HTTP {r.status}\n")
            if len(rs) > 20:
                out.write(f"- _… and {len(rs) - 20} more_\n")
            out.write("\n")

    # 2xx list (collapsed)
    if by_status.get("2xx"):
        out.write(
            f"<details><summary>Passing endpoints ({len(by_status['2xx'])})</summary>\n\n"
        )
        for r in sorted(by_status["2xx"], key=lambda r: (r.path, r.method)):
            out.write(f"- `{r.method} {r.path}` → {r.status}\n")
        out.write("\n</details>\n")

    return out.getvalue()


def to_csv(results: list[Result]) -> str:
    out = StringIO()
    writer = csv.writer(out)
    writer.writerow(
        [
            "method",
            "path",
            "status",
            "bucket",
            "exception_class",
            "exception_msg",
            "location",
            "payload_source",
            "body_excerpt",
        ]
    )
    for r in results:
        sig = r.signature
        writer.writerow(
            [
                r.method,
                r.path,
                r.status,
                sig.bucket_key() if sig else "",
                sig.exception_class if sig else "",
                sig.exception_msg if sig else "",
                sig.location if sig else "",
                r.payload_source,
                r.body_excerpt[:300],
            ]
        )
    return out.getvalue()
