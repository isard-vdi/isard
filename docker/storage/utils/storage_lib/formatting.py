# SPDX-License-Identifier: AGPL-3.0-or-later

from datetime import datetime


def format_size(size_bytes):
    """Format bytes into human-readable string (B/KB/MB/GB/TB/PB)."""
    if size_bytes == 0:
        return "0 B"
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


def format_time_remaining(seconds):
    """Format seconds into human-readable time string."""
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        minutes = int(seconds / 60)
        secs = int(seconds % 60)
        return f"{minutes}m {secs}s"
    else:
        hours = int(seconds / 3600)
        minutes = int((seconds % 3600) / 60)
        return f"{hours}h {minutes}m"


def log(message):
    """Print message with HH:MM:SS timestamp prefix."""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")


def size_gb(paths):
    """Calculate total size of paths in GB, rounded to 2 decimals."""
    from pathlib import Path

    total = 0
    for p in paths:
        p = Path(p)
        if p.is_file():
            total += p.stat().st_size
        elif p.is_dir():
            total += sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
    return round(total / (1024**3), 2)
