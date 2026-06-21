from __future__ import annotations

import unittest

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


if __name__ == "__main__":
    unittest.main()
