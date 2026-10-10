#!/usr/bin/env python3
"""Audit a small, explicit PPK2-style capture contract (standard library only)."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path


class EvidenceError(ValueError):
    pass


def audit(manifest_path: Path, samples_path: Path) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    required = {"schema", "sample_hz", "voltage_V", "boundary", "sample_count",
                "samples_sha256", "expected_gates", "data_kind"}
    if not required.issubset(manifest):
        raise EvidenceError(f"missing manifest fields: {sorted(required - manifest.keys())}")
    if manifest["schema"] != 1 or manifest["sample_hz"] != 100_000:
        raise EvidenceError("unsupported schema or sampling rate")
    voltage = manifest["voltage_V"]
    if not isinstance(voltage, (int, float)) or not math.isfinite(voltage) or voltage <= 0:
        raise EvidenceError("invalid supply voltage")
    if not isinstance(manifest["boundary"], str) or not manifest["boundary"].strip():
        raise EvidenceError("measurement boundary is required")
    if manifest["data_kind"] != "synthetic":
        raise EvidenceError("this public example accepts synthetic fixtures only")
    expected = manifest["expected_gates"]
    if not isinstance(expected, dict) or not expected or any(
        not isinstance(name, str) or not name or type(count) is not int or count <= 0
        for name, count in expected.items()
    ):
        raise EvidenceError("invalid gate-count declaration")
    raw = samples_path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != manifest["samples_sha256"]:
        raise EvidenceError("sample SHA-256 mismatch")

    energy = defaultdict(float)
    counts = Counter()
    closed = set()
    current_gate = ""
    active_gates = set()
    sample_rows = 0
    with samples_path.open(newline="", encoding="utf-8") as handle:
        rows = csv.DictReader(handle)
        if rows.fieldnames != ["index", "current_uA", "operation", "gate_id"]:
            raise EvidenceError("unexpected sample columns")
        for index, row in enumerate(rows):
            sample_rows += 1
            try:
                if int(row["index"]) != index:
                    raise EvidenceError("sample index gap or reorder")
                current = float(row["current_uA"])
            except (TypeError, ValueError) as exc:
                raise EvidenceError("invalid sample index or current") from exc
            if not math.isfinite(current) or current < 0:
                raise EvidenceError("nonfinite or negative current")
            operation, gate_id = row["operation"], row["gate_id"]
            if bool(operation) != bool(gate_id):
                raise EvidenceError("operation and gate ID must be present together")
            if operation and operation not in expected:
                raise EvidenceError("undeclared operation")
            gate = (operation, gate_id) if operation else ""
            if gate != current_gate:
                if current_gate:
                    closed.add(current_gate)
                if gate:
                    if gate in closed or gate in active_gates:
                        raise EvidenceError("gate ID repeated or noncontiguous")
                    counts[operation] += 1
                    active_gates.add(gate)
                current_gate = gate
            if operation:
                energy[operation] += current * voltage / manifest["sample_hz"]
    if type(manifest["sample_count"]) is not int or sample_rows != manifest["sample_count"]:
        raise EvidenceError("sample count mismatch")
    if dict(counts) != expected:
        raise EvidenceError(f"gate count mismatch: observed {dict(counts)}, expected {expected}")
    return {"status": "validated_synthetic_fixture", "samples_sha256": digest,
            "sample_count": manifest["sample_count"], "sample_hz": manifest["sample_hz"],
            "voltage_V": voltage, "boundary": manifest["boundary"],
            "gate_counts": dict(counts),
            "gross_energy_uJ_by_operation": {key: round(energy[key], 9) for key in sorted(expected)}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("samples", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(audit(args.manifest, args.samples), indent=2))
    except (EvidenceError, OSError, json.JSONDecodeError) as exc:
        parser.exit(1, f"evidence invalid: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
