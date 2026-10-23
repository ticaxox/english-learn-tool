from __future__ import annotations

import sys
import unittest
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_production_contract as contract  # noqa: E402

DIGEST = "@sha256:" + "a" * 64
APP = {
    "image": "ghcr.io/example/english-learn-api" + DIGEST,
    "read_only": True,
    "cap_drop": ["ALL"],
    "security_opt": ["no-new-privileges:true"],
    "logging": {"options": {"max-size": "10m", "max-file": "3"}},
    "mem_limit": 128 * 1024 * 1024,
}
CONFIG = {
    "services": {
        "postgres": {
            "image": "postgres:16-alpine" + DIGEST,
            "logging": {"options": {"max-size": "10m", "max-file": "3"}},
            "mem_limit": 96 * 1024 * 1024,
        },
        "redis": {
            "image": "redis:7-alpine" + DIGEST,
            "logging": {"options": {"max-size": "10m", "max-file": "3"}},
            "mem_limit": 32 * 1024 * 1024,
        },
        "migrate": deepcopy(APP),
        "api": deepcopy(APP),
        "worker": deepcopy(APP),
        "scheduler": deepcopy(APP),
        "frontend": {
            "image": "ghcr.io/example/english-learn-frontend" + DIGEST,
            "read_only": True,
            "cap_drop": ["ALL"],
            "security_opt": ["no-new-privileges:true"],
            "logging": {"options": {"max-size": "10m", "max-file": "3"}},
            "mem_limit": 20 * 1024 * 1024,
        },
        "reverse-proxy": {
            "image": "ghcr.io/example/english-learn-reverse-proxy" + DIGEST,
            "read_only": True,
            "cap_drop": ["ALL"],
            "security_opt": ["no-new-privileges:true"],
            "logging": {"options": {"max-size": "10m", "max-file": "3"}},
            "mem_limit": 20 * 1024 * 1024,
            "ports": [{"host_ip": "127.0.0.1", "published": "8080"}],
        },
    }
}


class ProductionContractTests(unittest.TestCase):
    def test_valid_contract(self) -> None:
        contract.validate_production_config(CONFIG, 1024)

    def test_mutable_image_is_rejected(self) -> None:
        data = deepcopy(CONFIG)
        data["services"]["api"]["image"] = "ghcr.io/example/english-learn-api:latest"
        with self.assertRaisesRegex(contract.ContractError, "digest-pinned"):
            contract.validate_production_config(data, 1024)

    def test_database_port_and_protected_edge_port_are_rejected(self) -> None:
        data = deepcopy(CONFIG)
        data["services"]["redis"]["ports"] = [{"host_ip": "0.0.0.0", "published": "6379"}]
        with self.assertRaisesRegex(contract.ContractError, "must not publish"):
            contract.validate_production_config(data, 1024)
        data = deepcopy(CONFIG)
        data["services"]["reverse-proxy"]["ports"][0]["published"] = "443"
        with self.assertRaisesRegex(contract.ContractError, "ports 80/443/30000"):
            contract.validate_production_config(data, 1024)

    def test_memory_budget_is_enforced(self) -> None:
        with self.assertRaisesRegex(contract.ContractError, "exceed"):
            contract.validate_production_config(CONFIG, 100)


if __name__ == "__main__":
    unittest.main()
