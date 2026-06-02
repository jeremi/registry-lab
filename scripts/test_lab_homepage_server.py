#!/usr/bin/env python3
"""Focused tests for the Registry Lab homepage server."""

from __future__ import annotations

import importlib.util
import os
import unittest
import urllib.error
from email.message import Message
from pathlib import Path
from unittest import mock

MODULE_PATH = Path(__file__).resolve().parent / "lab-homepage-server.py"
_spec = importlib.util.spec_from_file_location("lab_homepage_server", MODULE_PATH)
assert _spec and _spec.loader
server = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(server)


class ApplyEnvFileTest(unittest.TestCase):
    """apply_env_file must fill absent or empty vars, but never clobber a real value."""

    KEY = "REGISTRY_LAB_TEST_TOKEN_RAW"

    def setUp(self) -> None:
        self._saved = dict(os.environ)

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._saved)

    def test_fills_absent_key(self) -> None:
        os.environ.pop(self.KEY, None)
        server.apply_env_file({self.KEY: "from-file"})
        self.assertEqual(os.environ[self.KEY], "from-file")

    def test_fills_empty_key(self) -> None:
        # Compose injects each token as ${VAR:-}, so the key exists but is empty.
        os.environ[self.KEY] = ""
        server.apply_env_file({self.KEY: "from-file"})
        self.assertEqual(os.environ[self.KEY], "from-file")

    def test_non_empty_value_wins(self) -> None:
        os.environ[self.KEY] = "from-deploy-env"
        server.apply_env_file({self.KEY: "from-file"})
        self.assertEqual(os.environ[self.KEY], "from-deploy-env")


class StatusClassificationTest(unittest.TestCase):
    """A reachable, auth-gated service (401/403) is up, not down."""

    CONFIG = {
        "services": [
            {"id": "svc", "label": "Svc", "url": "https://svc.example", "status_path": "/x"}
        ]
    }

    def _check(self, fake_urlopen):
        with mock.patch.object(server.urllib.request, "urlopen", fake_urlopen):
            return server.status_checks(self.CONFIG, timeout=1.0)["checks"][0]

    def test_2xx_is_up(self) -> None:
        class Resp:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        check = self._check(lambda req, timeout=None: Resp())
        self.assertTrue(check["ok"])
        self.assertFalse(check["auth_gated"])
        self.assertEqual(check["status_code"], 200)

    def test_401_is_up_and_auth_gated(self) -> None:
        def fake(req, timeout=None):
            raise urllib.error.HTTPError("https://svc.example/x", 401, "Unauthorized", Message(), None)

        check = self._check(fake)
        self.assertTrue(check["ok"])
        self.assertTrue(check["auth_gated"])
        self.assertEqual(check["status_code"], 401)

    def test_403_is_up_and_auth_gated(self) -> None:
        def fake(req, timeout=None):
            raise urllib.error.HTTPError("https://svc.example/x", 403, "Forbidden", Message(), None)

        check = self._check(fake)
        self.assertTrue(check["ok"])
        self.assertTrue(check["auth_gated"])

    def test_5xx_is_down(self) -> None:
        def fake(req, timeout=None):
            raise urllib.error.HTTPError("https://svc.example/x", 503, "Unavailable", Message(), None)

        check = self._check(fake)
        self.assertFalse(check["ok"])
        self.assertFalse(check["auth_gated"])
        self.assertEqual(check["status_code"], 503)

    def test_transport_error_is_down(self) -> None:
        def fake(req, timeout=None):
            raise urllib.error.URLError("connection refused")

        check = self._check(fake)
        self.assertFalse(check["ok"])
        self.assertFalse(check["auth_gated"])
        self.assertIsNone(check["status_code"])


if __name__ == "__main__":
    unittest.main()
