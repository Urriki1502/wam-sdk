"""Public reports are constructed from an allowlist, never redacted raw logs."""

from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import unittest
import xml.etree.ElementTree as ET

from .errors import CODES, HarnessError
from .privacy import private_write


class SafeResult(unittest.TestResult):
    def __init__(self):
        super().__init__()
        self.rows = []

    def _row(self, test, status, code=""):
        case_id = getattr(test, "case_id", None)
        if not isinstance(case_id, str) or not re.fullmatch(r"[A-Z]{2,8}-[0-9]{3}", case_id):
            raise HarnessError("REPORT_INVALID")
        self.rows.append({"id": case_id, "status": status, "code": code})

    def addSuccess(self, test):
        super().addSuccess(test)
        self._row(test, "pass")

    def addFailure(self, test, err):
        # Do NOT call super(): unittest would format fixture-rich tracebacks.
        self.failures.append((test, "ASSERTION_FAILED"))
        self._row(test, "fail", "ASSERTION_FAILED")

    def addError(self, test, err):
        code = err[1].code if isinstance(err[1], HarnessError) else "TEST_ERROR"
        self.errors.append((test, code))
        self._row(test, "error", code)

    def addSkip(self, test, reason):
        self.skipped.append((test, "NOT_RUN"))
        self._row(test, "not_run", "NOT_RUN")

    def addExpectedFailure(self, test, err):
        # No expected-failure escape hatch for a privacy gate.
        self.failures.append((test, "ASSERTION_FAILED"))
        self._row(test, "fail", "ASSERTION_FAILED")

    def addUnexpectedSuccess(self, test):
        self.errors.append((test, "TEST_ERROR"))
        self._row(test, "error", "TEST_ERROR")

    def addSubTest(self, test, subtest, err):
        # Subtests can carry sensitive parameter values in generated identifiers.
        if err is not None:
            self.addFailure(test, err)


def build_report(rows, profile, binary_digest=None, run_error=None):
    if profile not in ("selftest", "regtest") or run_error not in CODES | {None}:
        raise HarnessError("REPORT_INVALID")
    if binary_digest is not None and not re.fullmatch(r"[0-9a-f]{64}", binary_digest):
        raise HarnessError("REPORT_INVALID")
    seen = set()
    cases = []
    for row in rows:
        if (set(row) != {"id", "status", "code"} or
                not re.fullmatch(r"[A-Z]{2,8}-[0-9]{3}", row["id"]) or row["id"] in seen or
                row["status"] not in ("pass", "fail", "error", "not_run") or
                row["code"] not in CODES | {""}):
            raise HarnessError("REPORT_INVALID")
        seen.add(row["id"])
        cases.append(dict(row))
    counts = Counter(r["status"] for r in cases)
    verdict = "pass" if cases and counts["pass"] == len(cases) and run_error is None else "fail"
    return {
        "schema_version": 1, "suite_version": "0.1.0", "profile": profile,
        "verdict": verdict, "run_error": run_error,
        "target_binary_sha256": binary_digest,
        "counts": {k: counts[k] for k in ("pass", "fail", "error", "not_run")},
        "cases": cases,
    }


def write_report(directory, report):
    # Validate again at the serialization boundary. Reject unknown fields.
    expected = build_report(report["cases"], report["profile"],
                            report["target_binary_sha256"], report["run_error"])
    if expected != report:
        raise HarnessError("REPORT_INVALID")
    directory = Path(directory)
    try:
        directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    except FileExistsError:
        raise HarnessError("REPORT_EXISTS") from None
    except OSError:
        raise HarnessError("REPORT_WRITE") from None
    try:
        private_write(directory / "summary.json", json.dumps(report, indent=2) + "\n")
        cases = report["cases"]
        root = ET.Element("testsuite", name="wam-sdk", tests=str(len(cases)),
                          failures=str(report["counts"]["fail"]),
                          errors=str(report["counts"]["error"] + bool(report["run_error"])),
                          skipped=str(report["counts"]["not_run"]))
        for row in cases:
            case = ET.SubElement(root, "testcase", classname=report["profile"], name=row["id"])
            if row["status"] != "pass":
                tag = {"fail": "failure", "error": "error", "not_run": "skipped"}[row["status"]]
                ET.SubElement(case, tag, message=row["code"])
        if report["run_error"]:
            case = ET.SubElement(root, "testcase", classname="harness", name="RUN-000")
            ET.SubElement(case, "error", message=report["run_error"])
            root.set("tests", str(len(cases) + 1))
        private_write(directory / "junit.xml", ET.tostring(root, encoding="unicode") + "\n")
    except OSError:
        raise HarnessError("REPORT_WRITE") from None


def scan_public(directory):
    """Reject added files/fields; this is a schema gate, not a magic secret detector."""
    directory = Path(directory)
    if {p.name for p in directory.iterdir()} != {"summary.json", "junit.xml"}:
        raise HarnessError("REPORT_INVALID")
    for p in directory.iterdir():
        if p.is_symlink() or not p.is_file() or p.stat().st_size > 256_000:
            raise HarnessError("REPORT_INVALID")
    report = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    expected = build_report(report["cases"], report["profile"],
                            report["target_binary_sha256"], report["run_error"])
    if expected != report:
        raise HarnessError("REPORT_INVALID")
    # Canonical comparison prevents embedding a secret in XML attributes/text.
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        canonical = Path(tmp) / "canonical"
        write_report(canonical, expected)
        if (directory / "junit.xml").read_bytes() != (canonical / "junit.xml").read_bytes():
            raise HarnessError("REPORT_INVALID")
    return report
