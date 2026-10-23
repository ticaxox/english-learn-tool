from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "deploy" / "scripts"
RELEASE_TEST = REPO_ROOT / "deploy" / "tests" / "test_release_manifest.py"


class DeploymentReceiptTests(unittest.TestCase):
    def test_receipt_contains_digests_and_no_secret_values(self) -> None:
        sys.path.insert(0, str(REPO_ROOT / "deploy" / "tests"))
        from test_release_manifest import VALID

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / "manifest.json"
            receipt = root / "deployment-evidence.json"
            manifest.write_text(json.dumps(VALID), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "write_deployment_receipt.py"),
                    "--manifest",
                    str(manifest),
                    "--output",
                    str(receipt),
                    "--profile",
                    "lightweight",
                    "--edge-bind",
                    "127.0.0.1",
                    "--edge-port",
                    "8080",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertEqual(data["event"], "deploy")
            self.assertEqual(data["release"], VALID["release"])
            self.assertTrue(data["images"]["api"].endswith("@" + VALID["images"]["api"].rsplit("@", 1)[1]))
            self.assertNotIn("password", json.dumps(data).lower())
            if os.name != "nt":
                self.assertEqual(os.stat(receipt).st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
