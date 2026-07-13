from __future__ import annotations

import io
import unittest
from argparse import Namespace
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from htb_terminal import cli


class CliDispatchTests(unittest.TestCase):
    def test_static_vpn_listing_needs_no_token(self) -> None:
        with (
            mock.patch("htb_terminal.cli.load_config") as load_config,
            redirect_stdout(io.StringIO()),
        ):
            code = cli.main(["vpn", "servers", "--static", "--color", "never"])

        self.assertEqual(0, code)
        load_config.assert_not_called()

    def test_live_vpn_listing_still_loads_auth(self) -> None:
        with mock.patch(
            "htb_terminal.cli.load_config",
            side_effect=RuntimeError("auth requested"),
        ) as load_config, redirect_stderr(io.StringIO()):
            code = cli.main(["vpn", "servers"])

        self.assertEqual(1, code)
        load_config.assert_called_once()

    def test_keyboard_interrupt_returns_standard_exit_code(self) -> None:
        args = Namespace(
            handler=mock.Mock(side_effect=KeyboardInterrupt),
            needs_auth=False,
        )
        parser = mock.Mock()
        parser.parse_args.return_value = args

        with (
            mock.patch("htb_terminal.cli.build_parser", return_value=parser),
            redirect_stderr(io.StringIO()) as stream,
        ):
            code = cli.main([])

        self.assertEqual(130, code)
        self.assertIn("interrupted", stream.getvalue())


if __name__ == "__main__":
    unittest.main()
