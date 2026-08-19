#!/usr/bin/env python
"""Sync the OpenKB wiki into landy_ai's kb/wiki/ for the V6 agent.

Copies everything under the OpenKB wiki root except sources/images/ (large,
unused by any V6 tool -- see
docs/superpowers/specs/2026-08-19-agent-v6-design.md). Run manually after
adding/recompiling a document in OpenKB, then commit + redeploy.

Usage:
    python scripts/sync_kb.py [--source PATH]
"""
import argparse
import shutil
from pathlib import Path

DEFAULT_SOURCE = Path(r"C:\Users\Yang Hui\Desktop\projects\openkb\my-kb\wiki")
DEST = Path(__file__).resolve().parent.parent / "kb" / "wiki"


def sync_kb(source: Path, dest: Path) -> None:
    if not source.is_dir():
        raise FileNotFoundError(f"Source wiki not found: {source}")
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(source, dest, ignore=shutil.ignore_patterns("images"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    args = parser.parse_args()
    sync_kb(args.source, DEST)
    print(f"Synced {args.source} -> {DEST}")


if __name__ == "__main__":
    main()
