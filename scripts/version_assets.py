#!/usr/bin/env python3
"""Version every docs asset reference with a content hash (?v=<sha1[:8]>)
and stamp the build hash on <html data-build>. Idempotent: re-running on
already-versioned files is a no-op. The Pages deploy runs this and FAILS if
it changes anything, so the deployed site can never differ from the repo.
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

DOCS = Path(__file__).resolve().parent.parent / "docs"
REF = re.compile(r'((?:src|href)=")(assets/[^"?]+)(?:\?v=[0-9a-f]+)?(")')


def asset_hash(path: Path) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest()[:8]


def version_docs() -> int:
    changed = 0
    assets = {p.name: p for p in (DOCS / "assets").iterdir() if p.is_file()}
    build = hashlib.sha1(
        b"".join(sorted(p.read_bytes() for p in assets.values()))
    ).hexdigest()[:8]
    for html in DOCS.glob("*.html"):
        src = html.read_text(encoding="utf-8")
        out = REF.sub(
            lambda m: (
                f"{m.group(1)}{m.group(2)}?v={asset_hash(DOCS / m.group(2))}{m.group(3)}"
            ),
            src,
        )
        out = re.sub(r'(<html[^>]*?)\sdata-build="[^"]*"', r"\1", out)
        out = out.replace("<html", f'<html data-build="{build}"', 1)
        if out != src:
            html.write_text(out, encoding="utf-8")
            changed += 1
    return changed


if __name__ == "__main__":  # pragma: no cover
    n = version_docs()
    print(f"versioned {n} html file(s); build hash stamped")
    sys.exit(0 if "--check" not in sys.argv or n == 0 else 1)
