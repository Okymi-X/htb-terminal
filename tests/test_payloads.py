from __future__ import annotations

import unittest

from htb_terminal.services.payloads import (
    academy_module_names,
    extract_items,
    has_next_page,
    machine_row,
    page_signature,
    to_int,
)


class ExtractItemsTests(unittest.TestCase):
    def test_returns_list_payload_as_is(self) -> None:
        self.assertEqual([1, 2], extract_items([1, 2]))

    def test_reads_known_wrapper_keys(self) -> None:
        self.assertEqual([{"id": 1}], extract_items({"message": [{"id": 1}]}))
        self.assertEqual([{"id": 2}], extract_items({"data": [{"id": 2}]}))

    def test_reads_nested_data_dict(self) -> None:
        self.assertEqual([{"id": 3}], extract_items({"info": {"data": [{"id": 3}]}}))

    def test_returns_empty_for_unknown_shapes(self) -> None:
        self.assertEqual([], extract_items(None))
        self.assertEqual([], extract_items({"unexpected": 1}))


class HasNextPageTests(unittest.TestCase):
    def test_links_next_takes_priority(self) -> None:
        self.assertTrue(has_next_page({"links": {"next": "url"}}, 1))
        self.assertFalse(has_next_page({"links": {"next": None}}, 1))

    def test_meta_last_page_is_compared_to_current(self) -> None:
        self.assertTrue(has_next_page({"meta": {"current_page": 1, "last_page": 3}}, 1))
        self.assertFalse(has_next_page({"meta": {"current_page": 3, "last_page": 3}}, 3))


class MachineRowTests(unittest.TestCase):
    def test_falls_back_to_play_info_state(self) -> None:
        row = machine_row({"id": 1, "name": "A", "playInfo": {"isActive": True, "isSpawned": False}})
        self.assertTrue(row["active"])
        self.assertFalse(row["spawned"])

    def test_prefers_top_level_difficulty_and_points_aliases(self) -> None:
        row = machine_row({"id": 1, "difficulty_text": "Hard", "static_points": 40})
        self.assertEqual("Hard", row["difficulty"])
        self.assertEqual(40, row["points"])


class MiscHelperTests(unittest.TestCase):
    def test_page_signature_is_stable_for_same_ids(self) -> None:
        items = [{"id": 1}, {"id": 2}]
        self.assertEqual(page_signature(items), page_signature([{"id": 1}, {"id": 2}]))

    def test_academy_module_names_extracts_names_only(self) -> None:
        self.assertEqual(["A"], academy_module_names([{"name": "A"}, {"id": 2}, "x"]))

    def test_to_int_returns_none_on_bad_input(self) -> None:
        self.assertEqual(5, to_int("5"))
        self.assertIsNone(to_int(None))
        self.assertIsNone(to_int("abc"))


if __name__ == "__main__":
    unittest.main()
