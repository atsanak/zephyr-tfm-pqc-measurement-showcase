import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from evidence import EvidenceError, audit


ROOT = Path(__file__).resolve().parents[1]


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.csv = self.base / "samples.csv"
        self.manifest = self.base / "capture.json"
        self.csv.write_bytes((ROOT / "examples/synthetic_samples.csv").read_bytes())
        self.data = json.loads((ROOT / "examples/synthetic_capture.json").read_text())
        self.manifest.write_text(json.dumps(self.data))

    def test_valid_capture(self):
        result = audit(self.manifest, self.csv)
        self.assertEqual(result["gate_counts"], {"keypair": 1, "sign": 1, "verify": 1})
        self.assertEqual(result["sample_count"], 12)
        self.assertAlmostEqual(result["gross_energy_uJ_by_operation"]["sign"], 0.01785)

    def test_changed_trace_rejected(self):
        self.csv.write_text(self.csv.read_text().replace("190,sign", "191,sign"))
        with self.assertRaisesRegex(EvidenceError, "SHA-256"):
            audit(self.manifest, self.csv)

    def test_missing_gate_rejected_with_matching_hash(self):
        self.csv.write_text(self.csv.read_text().replace("verify,v1", ","))
        self.data["samples_sha256"] = hashlib.sha256(self.csv.read_bytes()).hexdigest()
        self.manifest.write_text(json.dumps(self.data))
        with self.assertRaisesRegex(EvidenceError, "gate count"):
            audit(self.manifest, self.csv)

    def test_nonfinite_current_rejected(self):
        self.csv.write_text(self.csv.read_text().replace("190,sign", "nan,sign"))
        self.data["samples_sha256"] = hashlib.sha256(self.csv.read_bytes()).hexdigest()
        self.manifest.write_text(json.dumps(self.data))
        with self.assertRaisesRegex(EvidenceError, "nonfinite"):
            audit(self.manifest, self.csv)


if __name__ == "__main__":
    unittest.main()
