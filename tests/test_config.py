from __future__ import annotations

import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from htb_terminal.config import (
    DEFAULT_BASE_URL,
    ConfigError,
    load_config,
    load_token,
    save_token,
    user_token_path,
)


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

    def test_falls_back_to_sudo_user_token_under_sudo(self):
        # Under sudo HOME is /root; the token saved as the normal user must
        # still be found via SUDO_USER so `sudo htb speedrun` works.
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            sudo_home = tmp / "okymi"
            token = sudo_home / ".config" / "htb-terminal" / "token"
            token.parent.mkdir(parents=True)
            token.write_text("sudo-token\n", encoding="utf-8")
            root_home = tmp / "root"
            root_home.mkdir()
            work = tmp / "work"
            work.mkdir()

            prev = os.getcwd()
            os.chdir(work)
            try:
                env = {"HOME": str(root_home), "SUDO_USER": "okymi"}
                with (
                    mock.patch.dict("os.environ", env, clear=True),
                    mock.patch("pwd.getpwnam", return_value=mock.Mock(pw_dir=str(sudo_home))),
                ):
                    self.assertEqual("sudo-token", load_token())
            finally:
                os.chdir(prev)

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


class SaveTokenTests(unittest.TestCase):
    def test_saved_token_has_private_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "token"
            target.write_text("old")
            target.chmod(0o644)
            save_token("secret", target)
            if os.name == "posix":
                self.assertEqual(0o600, stat.S_IMODE(target.stat().st_mode))

    @unittest.skipUnless(hasattr(os, "fchmod"), "fchmod is unavailable")
    def test_save_fails_before_overwrite_if_permissions_cannot_be_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "token"
            target.write_text("keep")
            with (
                mock.patch("htb_terminal.files.os.fchmod", side_effect=PermissionError("denied")),
                self.assertRaisesRegex(RuntimeError, "securely write"),
            ):
                save_token("secret", target)
            self.assertEqual("keep", target.read_text())

    @unittest.skipUnless(hasattr(os, "O_NOFOLLOW"), "O_NOFOLLOW is unavailable")
    def test_save_rejects_symlink_without_changing_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "target"
            target.write_text("keep")
            link = Path(tmp) / "token"
            link.symlink_to(target)
            with self.assertRaisesRegex(RuntimeError, "securely write"):
                save_token("secret", link)
            self.assertEqual("keep", target.read_text())

    @unittest.skipUnless(hasattr(os, "link"), "hard links are unavailable")
    def test_save_rejects_hard_link_without_changing_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "target"
            target.write_text("keep")
            link = Path(tmp) / "token"
            os.link(target, link)
            with self.assertRaisesRegex(RuntimeError, "securely write"):
                save_token("secret", link)
            self.assertEqual("keep", target.read_text())

    def test_save_rejects_empty_bearer_and_embedded_whitespace(self):
        for token in ("Bearer ", "Authorization: ", "abc\ndef", "abc def"):
            with self.subTest(token=token), self.assertRaises(ConfigError):
                save_token(token)

    def test_save_writes_to_user_config_and_normalizes(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict("os.environ", {"XDG_CONFIG_HOME": tmp}, clear=True):
                path = save_token("Bearer secret-123")
                self.assertEqual(user_token_path(), path)
                self.assertEqual("secret-123", path.read_text(encoding="utf-8").strip())

    def test_saved_token_is_then_resolved_from_user_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / "work"
            work.mkdir()
            previous_cwd = Path.cwd()
            with mock.patch.dict("os.environ", {"XDG_CONFIG_HOME": tmp}, clear=True):
                save_token("saved-token")
                # From a directory with no ./api.token, resolution falls
                # through to the user config file written by save_token.
                os.chdir(work)
                try:
                    self.assertEqual("saved-token", load_token())
                finally:
                    os.chdir(previous_cwd)

    def test_save_to_explicit_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "nested" / "token"
            with mock.patch.dict("os.environ", {}, clear=True):
                path = save_token("abc", target)
                self.assertEqual(target, path)
                self.assertEqual("abc", load_token(target))

    def test_save_rejects_empty_token(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(ConfigError):
                save_token("   ")


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
