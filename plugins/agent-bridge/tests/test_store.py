from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent_bridge.store import BridgeError, BridgeStore


class BridgeStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = BridgeStore(Path(self.temp_dir.name) / "bridge.sqlite3")
        self.store.register_agent("demo", "architect", "Plans changes")
        self.store.register_agent("demo", "reviewer", "Reviews changes")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_request_claim_reply_round_trip(self) -> None:
        created = self.store.create_request(
            "demo", "architect", "reviewer", "Review this plan"
        )
        claimed = self.store.claim_request("demo", "reviewer")
        self.assertIsNotNone(claimed)
        assert claimed is not None
        self.assertEqual(created.request_id, claimed.request_id)
        self.assertEqual("delivered", claimed.status)

        replied = self.store.reply(
            "demo", "reviewer", claimed.request_id, "The plan is sound"
        )
        self.assertEqual("replied", replied.status)
        self.assertEqual("The plan is sound", replied.response)
        self.assertEqual("replied", self.store.get_request(created.request_id).status)

    def test_second_listener_cannot_double_claim_active_lease(self) -> None:
        self.store.create_request("demo", "architect", "reviewer", "Only once")
        self.assertIsNotNone(self.store.claim_request("demo", "reviewer", 300))
        self.assertIsNone(self.store.claim_request("demo", "reviewer", 300))

    def test_only_recipient_can_reply(self) -> None:
        created = self.store.create_request("demo", "architect", "reviewer", "Question")
        with self.assertRaisesRegex(BridgeError, "addressed agent"):
            self.store.reply("demo", "architect", created.request_id, "Invalid")

    def test_requester_can_cancel(self) -> None:
        created = self.store.create_request("demo", "architect", "reviewer", "Question")
        cancelled = self.store.cancel_request(
            "demo", "architect", created.request_id, "No longer needed"
        )
        self.assertEqual("cancelled", cancelled.status)
        self.assertEqual("No longer needed", cancelled.response)

    def test_project_isolation(self) -> None:
        self.store.register_agent("other", "reviewer")
        self.store.create_request("demo", "architect", "reviewer", "Demo only")
        self.assertIsNone(self.store.claim_request("other", "reviewer"))


if __name__ == "__main__":
    unittest.main()

