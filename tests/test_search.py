from __future__ import annotations

import unittest

from htb_terminal.services.search import machine_match_rank, searchable_machine_values


class MachineMatchRankTests(unittest.TestCase):
    def test_ranks_by_name_match_quality(self) -> None:
        self.assertEqual(0, machine_match_rank({"name": "Board"}, "board"))
        self.assertEqual(1, machine_match_rank({"name": "BoardLight"}, "board"))
        self.assertEqual(2, machine_match_rank({"name": "BlueBoard"}, "board"))

    def test_exact_field_match_outranks_substring(self) -> None:
        self.assertEqual(3, machine_match_rank({"name": "X", "os": "Linux"}, "linux"))

    def test_substring_in_searchable_values_is_lowest_rank(self) -> None:
        item = {"name": "X", "description": "breached credentials found"}
        self.assertEqual(4, machine_match_rank(item, "breached"))

    def test_returns_none_when_nothing_matches(self) -> None:
        self.assertIsNone(machine_match_rank({"name": "X", "os": "Linux"}, "windows"))


class SearchableValuesTests(unittest.TestCase):
    def test_includes_maker_and_tag_text(self) -> None:
        item = {
            "name": "X",
            "maker": {"name": "alice"},
            "tags": [{"name": "Kerberos"}, "smb"],
        }
        values = searchable_machine_values(item)
        self.assertIn("alice", values)
        self.assertIn("kerberos", values)
        self.assertIn("smb", values)

    def test_skips_none_values(self) -> None:
        self.assertNotIn("none", searchable_machine_values({"name": "X", "os": None}))


if __name__ == "__main__":
    unittest.main()
