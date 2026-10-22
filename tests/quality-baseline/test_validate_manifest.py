from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import validate_manifest as validator


class ValidateManifestTests(unittest.TestCase):
    def make_gate(self, **overrides: object) -> dict[str, object]:
        gate: dict[str, object] = {
            "id": "GATE-01",
            "title": "Synthetic gate",
            "source": ["T-QA-001"],
            "scope": "final",
            "layer": "unit",
            "owner": "A30",
            "preconditions": ["Synthetic preconditions"],
            "data": ["Synthetic data"],
            "command": ["python -m unittest"],
            "evidence": ["evidence.txt"],
            "status": "PASS",
            "reason": "Synthetic verification result.",
        }
        gate.update(overrides)
        return gate

    def make_manifest(self, gates: list[dict[str, object]] | None = None) -> dict[str, object]:
        return {
            "schema_version": 1,
            "task": "T-QA-001",
            "gates": gates or [self.make_gate()],
        }

    def test_valid_manifest_counts_statuses(self) -> None:
        manifest = self.make_manifest(
            [
                self.make_gate(id="GATE-01", status="PASS"),
                self.make_gate(id="GATE-02", status="NOT_RUN", evidence=["policy.txt"]),
            ]
        )

        errors, counts = validator.validate_manifest(manifest)

        self.assertEqual(errors, [])
        self.assertEqual(counts["PASS"], 1)
        self.assertEqual(counts["NOT_RUN"], 1)

    def test_contract_validation_reports_structural_errors(self) -> None:
        manifest = self.make_manifest(
            [
                self.make_gate(id="GATE-01"),
                self.make_gate(
                    id="GATE-01",
                    scope="unknown",
                    status="UNKNOWN",
                    evidence=[],
                ),
                self.make_gate(
                    id="GATE-03",
                    status="CONDITIONAL",
                    evidence=[],
                    conditions=[],
                ),
            ]
        )
        manifest["schema_version"] = 2

        errors, counts = validator.validate_manifest(manifest)

        joined = "\n".join(errors)
        self.assertIn("schema_version must be 1", joined)
        self.assertIn("duplicate gate id: GATE-01", joined)
        self.assertIn("scope must be one of", joined)
        self.assertIn("status must be one of", joined)
        self.assertIn("claims CONDITIONAL without evidence", joined)
        self.assertIn("no non-empty conditions list", joined)
        self.assertNotIn("UNKNOWN", counts)

    def test_workspace_root_checks_claimed_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "evidence.txt").write_text("synthetic evidence", encoding="utf-8")
            manifest = self.make_manifest([self.make_gate()])

            errors, _ = validator.validate_manifest(manifest, workspace_root=root)
            self.assertEqual(errors, [])

            (root / "evidence.txt").unlink()
            errors, _ = validator.validate_manifest(manifest, workspace_root=root)
            self.assertEqual(errors, ["gates[0] evidence missing: evidence.txt"])

    def test_repository_manifest_is_valid(self) -> None:
        manifest_path = Path(__file__).with_name("acceptance-gates.json")
        manifest = validator.load_manifest(manifest_path)

        errors, counts = validator.validate_manifest(manifest)

        self.assertEqual(errors, [])
        self.assertGreaterEqual(sum(counts.values()), 1)
        self.assertEqual(manifest["task"], "T-QA-001")

    def test_main_passes_normal_validation_and_rejects_final_incomplete(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text(
                json.dumps(
                    self.make_manifest(
                        [
                            self.make_gate(id="GATE-01", scope="final", status="NOT_RUN"),
                        ]
                    ),
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            normal_output = io.StringIO()
            with contextlib.redirect_stdout(normal_output):
                normal_exit = validator.main(["--manifest", str(path)])

            final_output = io.StringIO()
            with contextlib.redirect_stdout(final_output):
                final_exit = validator.main(
                    ["--manifest", str(path), "--require-final-pass"]
                )

        self.assertEqual(normal_exit, 0)
        self.assertIn("RESULT=PASS", normal_output.getvalue())
        self.assertEqual(final_exit, 1)
        self.assertIn("RESULT=FAIL", final_output.getvalue())
        self.assertIn("final gates not PASS: GATE-01", final_output.getvalue())


if __name__ == "__main__":
    unittest.main()
