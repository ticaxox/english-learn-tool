from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import validate_release_manifest as validator  # noqa: E402


VALID = {
    "schema_version": 1,
    "release": "v0.1.0-rc.1",
    "source_commit": "a" * 40,
    "created_at": "2026-10-24T00:00:00Z",
    "platform": "linux/amd64",
    "images": {
        "api": "ghcr.io/ticaxox/english-learn-api@sha256:" + "1" * 64,
        "frontend": "ghcr.io/ticaxox/english-learn-frontend@sha256:" + "2" * 64,
        "reverse_proxy": "ghcr.io/ticaxox/english-learn-reverse-proxy@sha256:" + "3" * 64,
    },
    "runtime_images": {
        "postgres": "postgres:16-alpine@sha256:" + "4" * 64,
        "redis": "redis:7-alpine@sha256:" + "5" * 64,
        "cloudflared": "cloudflare/cloudflared:2026.10.3@sha256:" + "6" * 64,
    },
}


class ReleaseManifestTests(unittest.TestCase):
    def test_valid_manifest_renders_pinned_environment(self) -> None:
        values = validator.validate_manifest(
            VALID, expected_release=VALID["release"], expected_commit=VALID["source_commit"]
        )
        rendered = validator.render_env(values)
        self.assertIn("API_IMAGE=ghcr.io/ticaxox/english-learn-api@sha256:", rendered)
        self.assertIn("POSTGRES_IMAGE=postgres:16-alpine@sha256:", rendered)
        self.assertNotIn("latest", rendered)

    def test_tag_only_application_reference_is_rejected(self) -> None:
        data = deepcopy(VALID)
        data["images"]["api"] = "ghcr.io/ticaxox/english-learn-api:v0.1.0"
        with self.assertRaisesRegex(validator.ManifestError, "digest-pinned"):
            validator.validate_manifest(data)

    def test_tag_only_runtime_reference_is_rejected(self) -> None:
        data = deepcopy(VALID)
        data["runtime_images"]["redis"] = "redis:7-alpine"
        with self.assertRaisesRegex(validator.ManifestError, "digest-pinned"):
            validator.validate_manifest(data)

    def test_wrong_image_name_and_mixed_owner_are_rejected(self) -> None:
        data = deepcopy(VALID)
        data["images"]["frontend"] = "ghcr.io/ticaxox/other@sha256:" + "2" * 64
        with self.assertRaisesRegex(validator.ManifestError, "english-learn-frontend"):
            validator.validate_manifest(data)
        data = deepcopy(VALID)
        data["images"]["frontend"] = "ghcr.io/other/english-learn-frontend@sha256:" + "2" * 64
        with self.assertRaisesRegex(validator.ManifestError, "same GHCR owner"):
            validator.validate_manifest(data)

    def test_expected_release_and_commit_mismatch_are_rejected(self) -> None:
        with self.assertRaisesRegex(validator.ManifestError, "release mismatch"):
            validator.validate_manifest(VALID, expected_release="v0.1.0")
        with self.assertRaisesRegex(validator.ManifestError, "source commit mismatch"):
            validator.validate_manifest(VALID, expected_commit="b" * 40)

    def test_write_env_is_private_and_round_trips(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "release.env"
            manifest = Path(directory) / "manifest.json"
            manifest.write_text(json.dumps(VALID), encoding="utf-8")
            self.assertEqual(
                validator.main(
                    [
                        str(manifest),
                        "--expected-release",
                        VALID["release"],
                        "--expected-commit",
                        VALID["source_commit"],
                        "--write-env",
                        str(target),
                    ]
                ),
                0,
            )
            if os.name != "nt":
                self.assertEqual(os.stat(target).st_mode & 0o777, 0o600)
            self.assertIn("REVERSE_PROXY_IMAGE=", target.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
