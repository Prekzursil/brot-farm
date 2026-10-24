"""CI gate for the research lab-notebook tree (research/probe-*/).

The research tree is a pre-publication lab notebook (receipts + results +
sources per probe). This gate enforces its record discipline without
executing any research compute:

  - results/*.json parse as JSON and are non-empty
  - receipts/*.md carry the skeleton sentinel within the first 5 lines
    ("If it still reads this way, ... no verdict here may be cited.")
  - src/*.py byte-compiles

Exits 1 with a per-file report on any failure.
"""

import json
import os
import py_compile
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESEARCH = os.path.join(REPO, "research")
SENTINEL = "If it still reads this way"
SENTINEL_LINES = 5


def fail(msg):
    print(f"  FAIL {msg}")
    return False


def check_receipts(probe_dir, name):
    ok = True
    rdir = os.path.join(probe_dir, "receipts")
    receipts = sorted(f for f in os.listdir(rdir) if f.endswith(".md")) if os.path.isdir(rdir) else []
    if not receipts:
        return fail(f"{name}: no receipts found (every probe ships dated receipts)")
    for r in receipts:
        path = os.path.join(rdir, r)
        with open(path, encoding="utf-8") as fh:
            head = [fh.readline() for _ in range(SENTINEL_LINES)]
        if not any(SENTINEL in line for line in head):
            ok = fail(f"{name}/receipts/{r}: skeleton sentinel not in first {SENTINEL_LINES} lines")
    return ok


def check_results(probe_dir, name):
    ok = True
    jdir = os.path.join(probe_dir, "results")
    if not os.path.isdir(jdir):
        return fail(f"{name}: no results/ directory (every probe ships machine-readable results)")
    results = sorted(f for f in os.listdir(jdir) if f.endswith(".json"))
    if not results:
        return fail(f"{name}: no result JSON files")
    for r in results:
        path = os.path.join(jdir, r)
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict) and not data:
                ok = fail(f"{name}/results/{r}: empty JSON object")
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            ok = fail(f"{name}/results/{r}: does not parse ({exc})")
    return ok


def check_sources(probe_dir, name):
    ok = True
    sdir = os.path.join(probe_dir, "src")
    if not os.path.isdir(sdir):
        return fail(f"{name}: no src/ directory (every probe ships its code)")
    sources = sorted(f for f in os.listdir(sdir) if f.endswith(".py"))
    if not sources:
        return fail(f"{name}: no Python sources")
    for s in sources:
        path = os.path.join(sdir, s)
        try:
            py_compile.compile(path, doraise=True)
        except py_compile.PyCompileError as exc:
            ok = fail(f"{name}/src/{s}: does not compile ({exc})")
    return ok


def main():
    if not os.path.isdir(RESEARCH):
        print("check-research: no research/ tree present - nothing to gate")
        return 0
    probes = sorted(d for d in os.listdir(RESEARCH) if os.path.isdir(os.path.join(RESEARCH, d)))
    if not probes:
        print("check-research: research/ tree is empty - nothing to gate")
        return 0
    print(f"check-research: {len(probes)} probe dir(s): {', '.join(probes)}")
    ok = True
    for name in probes:
        probe_dir = os.path.join(RESEARCH, name)
        for check in (check_receipts, check_results, check_sources):
            ok = check(probe_dir, name) and ok
    print("check-research: PASS" if ok else "check-research: FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
