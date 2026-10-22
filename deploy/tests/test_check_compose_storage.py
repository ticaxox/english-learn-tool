from __future__ import annotations

import copy
import unittest

from check_compose_storage import STORAGE_TARGET, ContractError, validate


def valid_config() -> dict:
    security = {
        "read_only": True,
        "cap_drop": ["ALL"],
        "security_opt": ["no-new-privileges:true"],
        "environment": {"WORDBOOK_STORAGE_DIR": STORAGE_TARGET},
    }
    storage_mount = {
        "type": "volume",
        "source": "project_wordbook-data",
        "target": STORAGE_TARGET,
        "read_only": False,
    }
    return {
        "name": "project",
        "services": {
            "postgres": {
                "volumes": [
                    {
                        "type": "volume",
                        "source": "project_postgres-data",
                        "target": "/var/lib/postgresql/data",
                    }
                ]
            },
            "redis": {
                "volumes": [
                    {
                        "type": "volume",
                        "source": "project_redis-data",
                        "target": "/data",
                    }
                ]
            },
            "migrate": {},
            "api": {
                **copy.deepcopy(security),
                "volumes": [copy.deepcopy(storage_mount)],
            },
            "worker": {
                **copy.deepcopy(security),
                "volumes": [copy.deepcopy(storage_mount)],
            },
            "scheduler": {
                **copy.deepcopy(security),
                "volumes": [copy.deepcopy(storage_mount)],
            },
            "frontend": {},
            "reverse-proxy": {
                "ports": [
                    {
                        "host_ip": "127.0.0.1",
                        "published": "8080",
                        "target": 8080,
                        "protocol": "tcp",
                    }
                ]
            },
        },
        "volumes": {
            "postgres-data": {"name": "project_postgres-data"},
            "redis-data": {"name": "project_redis-data"},
            "wordbook-data": {"name": "project_wordbook-data"},
        },
    }


class ComposeStorageContractTests(unittest.TestCase):
    def assert_contract_fails(self, config: dict, message: str) -> None:
        with self.assertRaisesRegex(ContractError, message):
            validate(config)

    def test_valid_contract(self) -> None:
        result = validate(valid_config())
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["shared_volume_source"], "project_wordbook-data")

    def test_services_must_share_a_source(self) -> None:
        config = valid_config()
        config["services"]["worker"]["volumes"][0]["source"] = "project_other-data"
        config["volumes"]["other-data"] = {"name": "project_other-data"}
        self.assert_contract_fails(config, "share one volume source")

    def test_bind_mount_is_rejected(self) -> None:
        config = valid_config()
        config["services"]["api"]["volumes"][0]["type"] = "bind"
        self.assert_contract_fails(config, "named volume|non-volume mount")

    def test_storage_environment_is_fixed(self) -> None:
        config = valid_config()
        config["services"]["scheduler"]["environment"]["WORDBOOK_STORAGE_DIR"] = (
            "/tmp/books"
        )
        self.assert_contract_fails(config, "WORDBOOK_STORAGE_DIR")

    def test_read_only_root_is_required(self) -> None:
        config = valid_config()
        config["services"]["worker"]["read_only"] = False
        self.assert_contract_fails(config, "read-only root filesystem")

    def test_extra_wordbook_consumer_is_rejected(self) -> None:
        config = valid_config()
        config["services"]["frontend"]["volumes"] = [
            {
                "type": "volume",
                "source": "project_wordbook-data",
                "target": "/usr/share/nginx/html/private",
            }
        ]
        self.assert_contract_fails(config, "must not receive")

    def test_non_loopback_port_is_rejected(self) -> None:
        config = valid_config()
        config["services"]["reverse-proxy"]["ports"][0]["host_ip"] = "0.0.0.0"
        self.assert_contract_fails(config, "non-loopback")

    def test_undeclared_named_volume_is_rejected(self) -> None:
        config = valid_config()
        del config["volumes"]["wordbook-data"]
        self.assert_contract_fails(config, "not declared")


if __name__ == "__main__":
    unittest.main()
