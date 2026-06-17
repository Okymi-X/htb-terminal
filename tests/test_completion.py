from __future__ import annotations

import unittest

from htb_terminal.completion import COMMANDS, completion_script


class CompletionTests(unittest.TestCase):
    def test_bash_script_lists_top_level_commands(self) -> None:
        script = completion_script("bash")
        self.assertIn("complete -F _htb_complete htb htbx", script)
        for command in COMMANDS:
            self.assertIn(command, script)

    def test_zsh_script_has_compdef(self) -> None:
        script = completion_script("zsh")
        self.assertIn("#compdef htb htbx", script)
        self.assertIn("compadd", script)

    def test_machine_subcommands_present(self) -> None:
        script = completion_script("bash")
        for sub in ("extend", "info", "active", "search"):
            self.assertIn(sub, script)

    def test_unknown_shell_raises(self) -> None:
        with self.assertRaises(ValueError):
            completion_script("fish")


if __name__ == "__main__":
    unittest.main()
