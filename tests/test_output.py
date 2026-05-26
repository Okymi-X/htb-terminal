from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import unittest

from htb_terminal.output import print_pretty, print_table


class OutputTests(unittest.TestCase):
    def test_pretty_prints_dict_without_json_noise(self) -> None:
        stream = StringIO()

        with redirect_stdout(stream):
            print_pretty(
                {
                    "info": {
                        "id": 669,
                        "name": "RustyKey",
                        "active": True,
                        "description": None,
                        "info_status": "Credentials are provided for the initial account.",
                    }
                },
                color="never",
            )

        output = stream.getvalue()
        self.assertIn("info", output)
        self.assertIn("active", output)
        self.assertIn("yes", output)
        self.assertIn("info_status", output)
        self.assertNotIn("{", output)
        self.assertNotIn("description", output)

    def test_table_can_force_color(self) -> None:
        stream = StringIO()

        with redirect_stdout(stream):
            print_table([{"id": 1, "active": True}], ["id", "active"], color="always")

        output = stream.getvalue()
        self.assertIn("\033[", output)
        self.assertIn("yes", output)


if __name__ == "__main__":
    unittest.main()
