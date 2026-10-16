from __future__ import annotations

import io
import unittest
from argparse import Namespace
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from htb_terminal import cli
from htb_terminal.http import ApiError


class CliDispatchTests(unittest.TestCase):
    def test_empty_live_vpn_pool_does_not_show_static_aliases(self) -> None:
        payload = {"data": {"options": {}, "assigned": None}}
        with (
            mock.patch("htb_terminal.cli.load_config"),
            mock.patch("htb_terminal.handlers._vpn_service") as service,
            redirect_stdout(io.StringIO()) as stream,
        ):
            service.return_value.list_servers.return_value = payload
            code = cli.main(["vpn", "servers", "release_arena", "--json"])
        self.assertEqual(0, code)
        self.assertIn('"options": {}', stream.getvalue())
        self.assertNotIn("eu-free-1", stream.getvalue())

    def test_live_vpn_outage_still_warns_and_shows_static_aliases(self) -> None:
        with (
            mock.patch("htb_terminal.cli.load_config"),
            mock.patch("htb_terminal.handlers._vpn_service") as service,
            redirect_stdout(io.StringIO()) as stream,
            redirect_stderr(io.StringIO()) as errors,
        ):
            service.return_value.list_servers.side_effect = ApiError(503, "unavailable")
            code = cli.main(["vpn", "servers", "--color", "never"])
        self.assertEqual(0, code)
        self.assertIn("showing built-in aliases", errors.getvalue())
        self.assertIn("eu-free-1", stream.getvalue())

    def test_vpn_connect_nonzero_exit_fails_cli(self) -> None:
        with (
            mock.patch("htb_terminal.cli.load_config"),
            mock.patch("htb_terminal.handlers._vpn_service") as service,
            redirect_stderr(io.StringIO()) as errors,
        ):
            service.return_value.connect.return_value = 15
            code = cli.main(["vpn", "connect", "113"])
        self.assertEqual(1, code)
        self.assertIn("OpenVPN exited with code 15", errors.getvalue())

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
