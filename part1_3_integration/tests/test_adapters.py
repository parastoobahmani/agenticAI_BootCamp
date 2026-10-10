import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator

from part1_3_integration import (
    ContractError,
    evidence_synthesis_to_analysis_input,
    part3_response_to_action_request,
    part3_response_to_human_approval_v2_seed,
    part3_response_to_memory_seed,
)


ROOT = Path(__file__).resolve().parents[2]


class AdapterTests(unittest.TestCase):
    def test_synthesis_output_validates_as_ali_analysis_input(self):
        case = {"case_id": "c1", "title": "A case", "body": "It fails."}
        synthesis = {
            "evidence_used": [{
                "score": 0.8, "claim_type": "hypothesis", "extracted_claim": "Possible cause",
                "citation": "source section", "relevance_reason": "similar symptoms",
                "source_id": "issue-1", "source_type": "past_report", "url": "Issue one",
            }],
            "hypotheses": [{"claim": "Possible cause", "citation": "source section"}],
        }
        result = evidence_synthesis_to_analysis_input(case, synthesis)
        schema = json.loads((ROOT/'part1_3_integration/schemas/analysis_input.schema.json').read_text())
        Draft202012Validator(schema).validate(result)
        self.assertEqual(result["evidence_bundle"]["hypotheses"][0]["confidence"], 0.0)
        self.assertEqual(result["evidence_bundle"]["evidence"][0]["source_type"], "issue")

    def test_part3_response_becomes_memory_branch_case_state(self):
        response = json.loads((ROOT/'part1_3_output/example_part1_3_output.json').read_text())
        report = json.loads((ROOT/'part1_2_output/example_part1_2_output.json').read_text())
        analysis_input = {
            "case": {"case_id": response["case_id"], "title": "Widget reset", "body": "Original body", "comments": []},
            "evidence_bundle": {"evidence": [{
                "evidence_id": "doc-widget-17", "source_type": "doc", "title": "Widgets",
                "url": "docs/widgets", "snippet": "Widget lifecycle", "relevance": 0.8,
            }], "hypotheses": []},
        }
        seed = part3_response_to_memory_seed(response, analysis_input)
        self.assertEqual(seed["case_id"], report["case_id"])
        self.assertEqual(seed["title"], "Widget reset")
        self.assertEqual(seed["proposals"][0]["action"], "comment")
        self.assertEqual(seed["proposals"][0]["payload"]["body"], response["user_response"])
        self.assertEqual(seed["proposals"][0]["status"], "pending")
        self.assertIn(response["id"], seed["proposals"][0]["rationale"])
        self.assertIn(response["input_fingerprint"], seed["proposals"][0]["rationale"])
        self.assertEqual(seed["sources"][0]["ref"], "doc-widget-17")

    def test_memory_join_rejects_cross_case_mix(self):
        response = json.loads((ROOT/'part1_3_output/example_part1_3_output.json').read_text())
        with self.assertRaises(ContractError):
            part3_response_to_memory_seed(response, {
                "case": {"case_id": "another-case"},
                "evidence_bundle": {"evidence": []},
            })

    def test_part3_response_becomes_human_approval_v2_state(self):
        response = json.loads((ROOT/'part1_3_output/example_part1_3_output.json').read_text())
        seed = part3_response_to_human_approval_v2_seed(response)
        proposal = seed["proposals"][0]
        self.assertEqual(seed["case_id"], response["case_id"])
        self.assertEqual(seed["version"], 1)
        self.assertEqual(seed["approvals"], [])
        self.assertEqual(proposal["case_version"], 1)
        self.assertEqual(proposal["action"], "comment")
        self.assertEqual(proposal["payload"]["body"], response["user_response"])
        self.assertEqual(len(proposal["action_hash"]), 64)
        self.assertEqual(proposal["status"], "pending")

    def test_later_part3_revision_becomes_action_request_without_guessing_version(self):
        response = json.loads((ROOT/'part1_3_output/example_part1_3_output.json').read_text())
        request = part3_response_to_action_request(response)
        self.assertEqual(request["case_id"], response["case_id"])
        self.assertEqual(request["action"], "comment")
        self.assertEqual(request["payload"], {"body": response["user_response"]})
        self.assertIn(response["id"], request["rationale"])
        self.assertNotIn("case_version", request)


if __name__ == "__main__":
    unittest.main()
