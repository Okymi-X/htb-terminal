from __future__ import annotations

import unittest
from contextlib import redirect_stderr
from io import StringIO

from htb_terminal.parser import build_parser


class GlobalFlagInheritanceTests(unittest.TestCase):
    def test_global_flags_accepted_after_subcommand(self) -> None:
        args = build_parser().parse_args(["machine", "list", "--json", "--color", "never"])
        self.assertTrue(args.json)
        self.assertEqual("never", args.color)

    def test_global_flags_accepted_before_subcommand(self) -> None:
        args = build_parser().parse_args(["--json", "--color", "never", "machine", "list"])
        self.assertTrue(args.json)
        self.assertEqual("never", args.color)

    def test_flag_before_subcommand_is_not_clobbered_by_subparser_default(self) -> None:
        # The subparser copies use SUPPRESS defaults, so a flag given before the
        # subcommand survives even when it is absent after it.
        args = build_parser().parse_args(["--json", "user", "info"])
        self.assertTrue(args.json)

    def test_defaults_present_when_flag_given_nowhere(self) -> None:
        args = build_parser().parse_args(["machine", "list"])
        self.assertFalse(args.json)
        self.assertEqual("auto", args.color)
        self.assertEqual(30, args.timeout)

    def test_nested_leaf_inherits_globals(self) -> None:
        args = build_parser().parse_args(["vpn", "switch", "eu-free-1", "--wide"])
        self.assertTrue(args.wide)
        self.assertEqual("eu-free-1", args.server)

    def test_rejects_invalid_numeric_options_during_parsing(self) -> None:
        invalid_commands = (
            ["--timeout", "0", "machine", "list"],
            ["machine", "list", "--page", "0"],
            ["machine", "search", "x", "--limit", "0"],
            ["machine", "start", "1", "--wait", "--interval", "0"],
            ["machine", "submit", "1", "flag", "--difficulty", "15"],
            ["vpn", "download", "1", "--variant", "-1"],
            ["speedrun", "1", "1", "--mtu", "0"],
        )

        for command in invalid_commands:
            with self.subTest(command=command), redirect_stderr(StringIO()):
                with self.assertRaises(SystemExit) as ctx:
                    build_parser().parse_args(command)
                self.assertEqual(2, ctx.exception.code)


if __name__ == "__main__":
    unittest.main()
