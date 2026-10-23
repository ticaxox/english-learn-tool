from __future__ import annotations

import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PROXY_CONF = REPO_ROOT / "deploy" / "reverse-proxy" / "nginx.conf"
FRONTEND_CONF = REPO_ROOT / "deploy" / "frontend" / "nginx.conf"

SECURITY_HEADERS = (
    "X-Content-Type-Options nosniff",
    "Referrer-Policy strict-origin-when-cross-origin",
    "X-Frame-Options SAMEORIGIN",
    "Content-Security-Policy",
    "Strict-Transport-Security",
)
CSP_DIRECTIVES = (
    "default-src 'self'",
    "base-uri 'self'",
    "object-src 'none'",
    "frame-ancestors 'self'",
    "form-action 'self'",
    "script-src 'self'",
    "connect-src 'self'",
    "worker-src 'self' blob:",
)


class NginxSecurityContractTests(unittest.TestCase):
    def test_both_edge_configs_preserve_security_headers_and_add_csp(self) -> None:
        for path in (PROXY_CONF, FRONTEND_CONF):
            with self.subTest(path=path.name):
                config = path.read_text(encoding="utf-8")
                for header in SECURITY_HEADERS:
                    self.assertIn(header, config)
                csp_line = next(
                    line for line in config.splitlines() if "Content-Security-Policy" in line
                )
                for directive in CSP_DIRECTIVES:
                    self.assertIn(directive, csp_line)
                self.assertNotIn("'unsafe-eval'", csp_line)
                self.assertNotIn("https:", csp_line)

    def test_sse_route_disables_buffering_and_keeps_security_headers(self) -> None:
        config = PROXY_CONF.read_text(encoding="utf-8")
        marker = "location ^~ /api/v1/coach/streams/"
        start = config.index(marker)
        end = config.index("location ^~ /api/", start + len(marker))
        block = config[start:end]
        self.assertIn("proxy_buffering off;", block)
        self.assertIn("proxy_cache off;", block)
        self.assertIn("gzip off;", block)
        self.assertIn("X-Accel-Buffering no", block)
        self.assertIn("no-cache, no-store", block)
        self.assertGreaterEqual(block.count("Content-Security-Policy"), 1)
        self.assertIn("X-Content-Type-Options nosniff", block)
        self.assertIn("Referrer-Policy strict-origin-when-cross-origin", block)
        self.assertIn("X-Frame-Options SAMEORIGIN", block)
        self.assertIn("Strict-Transport-Security", block)

    def test_private_wordbooks_are_not_served_by_edge(self) -> None:
        for path in (PROXY_CONF, FRONTEND_CONF):
            config = path.read_text(encoding="utf-8").lower()
            self.assertNotIn("/app/var/wordbooks", config)
            self.assertNotIn("wordbook-data", config)


if __name__ == "__main__":
    unittest.main()
