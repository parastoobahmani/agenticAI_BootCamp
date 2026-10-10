from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from problem2_parts1_2.evidence import EvidenceStore
from problem2_parts1_2.interceptor import TicketInterceptor
from problem2_parts1_2.orchestrator import Orchestrator
from problem2_parts1_2.storage import Storage


class HumanApprovalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.storage = Storage(root / "test.sqlite3")
        self.interceptor = TicketInterceptor(root / "ticket.json")
        self.app = Orchestrator(self.storage, self.interceptor, EvidenceStore())
        self.app.open_case("1", title="Test")

    def tearDown(self):
        self.storage.close()
        self.tmp.cleanup()

    def propose(self):
        d = self.app.handle_user_message(
            "1", "Streamlit 1.35.0 on Linux, running locally, my app is slow"
        )
        self.assertEqual(d.kind, "PROPOSE")
        return d.proposal_id

    def test_reject_never_executes(self):
        pid = self.propose()
        self.assertTrue(self.app.reject("1", pid)["ok"])
        result = self.app.execute("1", pid, "")
        self.assertFalse(result["ok"])
        self.assertEqual(self.interceptor.get("1")["comments"], [])

    def test_approval_allows_exact_execution(self):
        pid = self.propose()
        approval = self.app.approve("1", pid)
        self.assertTrue(approval["ok"])
        result = self.app.execute("1", pid, approval["approval_token"])
        self.assertTrue(result["ok"])
        self.assertTrue(result["result"]["executed"])
        self.assertEqual(len(self.interceptor.get("1")["comments"]), 1)

    def test_stale_approval_is_blocked(self):
        pid = self.propose()
        approval = self.app.approve("1", pid)
        self.app.memory.add_fact("1", "streamlit_version", "1.36.0", "user-correction")
        result = self.app.execute("1", pid, approval["approval_token"])
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "stale_approval")
        self.assertEqual(len(self.interceptor.get("1")["comments"]), 0)

    def test_duplicate_execution_is_idempotent(self):
        pid = self.propose()
        token = self.app.approve("1", pid)["approval_token"]
        first = self.app.execute("1", pid, token)
        second = self.app.execute("1", pid, token)
        self.assertTrue(first["result"]["executed"])
        self.assertTrue(second["result"]["duplicate"])
        self.assertEqual(len(self.interceptor.get("1")["comments"]), 1)

    def test_edit_approves_the_edited_action(self):
        pid = self.propose()
        edited = self.app.edit("1", pid, "comment", {"body": "Human-edited reply"})
        self.assertTrue(edited["ok"])
        result = self.app.execute("1", pid, edited["approval_token"])
        self.assertTrue(result["ok"])
        self.assertEqual(self.interceptor.get("1")["comments"][0]["body"], "Human-edited reply")

    def test_token_from_another_case_is_rejected(self):
        pid = self.propose()
        token = self.app.approve("1", pid)["approval_token"]
        self.app.open_case("2", title="Other")
        d = self.app.handle_user_message("2", "Streamlit 1.35.0 on Linux, running locally, other issue")
        other_token = self.app.approve("2", d.proposal_id)["approval_token"]
        result = self.app.execute("1", pid, other_token)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "invalid_approval")
        self.assertEqual(len(self.interceptor.get("1")["comments"]), 0)


if __name__ == "__main__":
    unittest.main()
