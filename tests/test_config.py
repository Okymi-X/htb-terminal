from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from htb_terminal.config import DEFAULT_BASE_URL, ConfigError, load_config, load_token


class TokenLoadingTests(unittest.TestCase):
    def test_loads_token_from_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            token_file = Path(tmp) / "api.token"
            token_file.write_text("file-token\n", encoding="utf-8")
            with mock.patch.dict("os.environ", {}, clear=True):
                self.assertEqual("file-token", load_token(token_file))

    def test_env_var_takes_precedence_over_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            token_file = Path(tmp) / "api.token"
            token_file.write_text("file-token", encoding="utf-8")
            with mock.patch.dict("os.environ", {"HTB_API_TOKEN": "env-token"}):
                self.assertEqual("env-token", load_token(token_file))

    def test_strips_bearer_and_authorization_prefixes(self):
        with mock.patch.dict("os.environ", {"HTB_API_TOKEN": "Authorization: Bearer abc123"}):
            self.assertEqual("abc123", load_token())

    def test_missing_token_raises_config_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "api.token"
            with mock.patch.dict("os.environ", {}, clear=True):
                with self.assertRaises(ConfigError):
                    load_token(missing)

    def test_empty_token_file_raises_config_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            token_file = Path(tmp) / "api.token"
            token_file.write_text("   \n", encoding="utf-8")
            with mock.patch.dict("os.environ", {}, clear=True):
                with self.assertRaises(ConfigError):
                    load_token(token_file)


class ConfigTests(unittest.TestCase):
    def test_default_base_url_with_trailing_slash_stripped(self):
        with mock.patch.dict("os.environ", {"HTB_API_TOKEN": "t"}, clear=True):
            config = load_config(base_url="https://example.test/api/v4/")
            self.assertEqual("https://example.test/api/v4", config.base_url)

    def test_uses_default_base_url(self):
        with mock.patch.dict("os.environ", {"HTB_API_TOKEN": "t"}, clear=True):
            config = load_config()
            self.assertEqual(DEFAULT_BASE_URL, config.base_url)


if __name__ == "__main__":
    unittest.main()
