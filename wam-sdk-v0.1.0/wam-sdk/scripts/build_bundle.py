#!/usr/bin/env python3
"""Deterministic source bundle with an explicit file allowlist and SHA-256 manifest."""
import argparse
import hashlib
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from devtools.report import scan_public


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    for profile in ("selftest", "regtest"):
        report = scan_public(ROOT / "reports" / profile)
        if report["verdict"] != "pass":
            raise ValueError("Evidence must pass before packaging")
    paths = {ROOT / name for name in ("README.md", "LICENSE", "pyproject.toml", ".gitignore")}
    for folder in ("src/wam_sdk", "devtools", "examples", "tests", "scripts"):
        paths.update((ROOT / folder).glob("*.py"))
    paths.add(ROOT / "src/wam_sdk/py.typed")
    paths.update((ROOT / "docs").glob("*.md"))
    paths.add(ROOT / ".github/workflows/ci.yml")
    wheel = ROOT / "dist/wam_sdk-0.1.0-py3-none-any.whl"
    paths.add(wheel)
    for profile in ("selftest", "regtest"):
        paths.update(ROOT / "reports" / profile / name for name in ("summary.json", "junit.xml"))
    data = {}
    for path in sorted(paths):
        if path.is_symlink() or not path.is_file():
            raise ValueError("Missing or unapproved bundle member")
        data[path.relative_to(ROOT).as_posix()] = path.read_bytes()
    data["MANIFEST.sha256"] = "".join(
        f"{hashlib.sha256(raw).hexdigest()}  {name}\n" for name, raw in sorted(data.items())
    ).encode()
    # Exclusive creation prevents overwriting an earlier reviewed deliverable.
    with zipfile.ZipFile(args.output, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, raw in sorted(data.items()):
            entry = zipfile.ZipInfo("wam-sdk/" + name, date_time=(2026, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, raw)
    print(f"Created source bundle with {len(data)} files")


if __name__ == "__main__":
    main()
