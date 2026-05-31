"""
Tool registry tests — verifies deterministic tool behaviour.

All tools in the registry use mock implementations that return fixed,
predictable values.  These tests document and protect those contracts
so future changes to the mock behaviour are caught immediately.

Covers:
  • payment_lookup — known payment PAY-10291 always returns CARD_DECLINED
  • payment_lookup — response structure (all required fields)
  • risk_check     — PAY-10291 always scores 28 / "low"
  • ticket_creator — always returns a TKT-prefixed ticket ID
  • customer_lookup, knowledge_base_search, email_sender — smoke tests
  • Unknown tool   — returns a structured error (does not raise)
  • Tools with missing args — handle gracefully without crashing
"""

import pytest
from app.tools.registry import execute_tool


# ── payment_lookup ────────────────────────────────────────────────────────────

class TestPaymentLookup:
    def test_known_payment_returns_card_declined(self):
        result = execute_tool("payment_lookup", payment_id="PAY-10291")
        assert result["error_code"] == "CARD_DECLINED"

    def test_payment_id_echoed_back(self):
        result = execute_tool("payment_lookup", payment_id="PAY-10291")
        assert result["payment_id"] == "PAY-10291"

    def test_result_includes_status(self):
        result = execute_tool("payment_lookup", payment_id="PAY-10291")
        assert "status" in result
        assert result["status"] in ("failed", "success", "pending", "declined")

    def test_result_includes_gateway(self):
        result = execute_tool("payment_lookup", payment_id="PAY-10291")
        assert "gateway" in result           # e.g. "PayBR_v2"

    def test_result_includes_error_message(self):
        result = execute_tool("payment_lookup", payment_id="PAY-10291")
        assert "error_message" in result
        assert len(result["error_message"]) > 0

    def test_deterministic_for_same_payment_id(self):
        """Same payment ID must always return the same error code."""
        r1 = execute_tool("payment_lookup", payment_id="PAY-10291")
        r2 = execute_tool("payment_lookup", payment_id="PAY-10291")
        assert r1["error_code"] == r2["error_code"]

    def test_unknown_payment_id_returns_structured_result(self):
        """Unknown payment IDs should still return a structured dict, not raise."""
        result = execute_tool("payment_lookup", payment_id="PAY-UNKNOWN-999")
        assert isinstance(result, dict)
        assert "payment_id" in result


# ── risk_check ────────────────────────────────────────────────────────────────

class TestRiskCheck:
    def test_pfi_payment_score_is_28(self):
        result = execute_tool("risk_check", payment_id="PAY-10291")
        assert result["risk_score"] == 28

    def test_pfi_payment_level_is_low(self):
        result = execute_tool("risk_check", payment_id="PAY-10291")
        assert result["risk_level"] == "low"

    def test_result_includes_aml_flags(self):
        result = execute_tool("risk_check", payment_id="PAY-10291")
        assert "aml_flags" in result         # list of AML flag strings

    def test_result_includes_recommendation(self):
        result = execute_tool("risk_check", payment_id="PAY-10291")
        assert "recommendation" in result
        assert len(result["recommendation"]) > 0

    def test_risk_score_in_valid_range(self):
        result = execute_tool("risk_check", payment_id="PAY-10291")
        score = result["risk_score"]
        assert 0 <= score <= 100

    def test_deterministic_for_same_payment(self):
        r1 = execute_tool("risk_check", payment_id="PAY-10291")
        r2 = execute_tool("risk_check", payment_id="PAY-10291")
        assert r1["risk_score"] == r2["risk_score"]


# ── ticket_creator ────────────────────────────────────────────────────────────

class TestTicketCreator:
    def test_returns_ticket_id(self):
        result = execute_tool("ticket_creator",
                              payment_id="PAY-10291", issue_type="payment_failure")
        assert "ticket_id" in result
        assert result["ticket_id"] is not None

    def test_ticket_id_has_tkt_prefix(self):
        result = execute_tool("ticket_creator",
                              payment_id="PAY-10291", issue_type="payment_failure")
        assert result["ticket_id"].startswith("TKT-"), \
            f"ticket_id does not start with 'TKT-': {result['ticket_id']}"

    def test_ticket_id_is_string(self):
        result = execute_tool("ticket_creator",
                              payment_id="PAY-10291", issue_type="payment_failure")
        assert isinstance(result["ticket_id"], str)

    def test_result_includes_status(self):
        result = execute_tool("ticket_creator",
                              payment_id="PAY-10291", issue_type="payment_failure")
        assert "status" in result

    def test_result_includes_payment_id(self):
        result = execute_tool("ticket_creator",
                              payment_id="PAY-99999", issue_type="test")
        assert "payment_id" in result
        assert result["payment_id"] == "PAY-99999"

    def test_different_calls_may_have_different_ids(self):
        """The mock assigns random TKT- IDs so two calls should differ."""
        r1 = execute_tool("ticket_creator", payment_id="PAY-A", issue_type="x")
        r2 = execute_tool("ticket_creator", payment_id="PAY-B", issue_type="x")
        # Different payment IDs → highly likely different ticket IDs
        # (mock is random, so we just verify both are valid)
        assert r1["ticket_id"].startswith("TKT-")
        assert r2["ticket_id"].startswith("TKT-")


# ── Other tools — smoke tests ─────────────────────────────────────────────────

class TestOtherTools:
    def test_customer_lookup_returns_dict(self):
        result = execute_tool("customer_lookup", customer_id="CUST-001")
        assert isinstance(result, dict)

    def test_knowledge_base_search_returns_dict(self):
        result = execute_tool("knowledge_base_search", query="payment failure CARD_DECLINED")
        assert isinstance(result, dict)

    def test_email_sender_returns_dict(self):
        result = execute_tool("email_sender",
                              to="customer@example.com", subject="test", body="hi")
        assert isinstance(result, dict)

    def test_sms_sender_returns_dict(self):
        result = execute_tool("sms_sender", to="+1234567890", message="test")
        assert isinstance(result, dict)

    def test_sanctions_checker_returns_dict(self):
        result = execute_tool("sanctions_checker", entity="ACME Corp")
        assert isinstance(result, dict)

    def test_kyc_lookup_returns_dict(self):
        result = execute_tool("kyc_lookup", customer_id="KYC-001")
        assert isinstance(result, dict)

    def test_bank_account_verifier_returns_dict(self):
        result = execute_tool("bank_account_verifier", account_number="1234567890")
        assert isinstance(result, dict)

    def test_refund_initiator_returns_dict(self):
        result = execute_tool("refund_initiator",
                              payment_id="PAY-10291", amount=50.00)
        assert isinstance(result, dict)


# ── Error handling ────────────────────────────────────────────────────────────

class TestToolErrorHandling:
    def test_unknown_tool_returns_error_dict(self):
        """execute_tool must never raise — always return a dict."""
        result = execute_tool("completely_nonexistent_tool_xyz")
        assert isinstance(result, dict)
        assert "error" in result

    def test_unknown_tool_error_mentions_tool_name(self):
        result = execute_tool("tool_that_does_not_exist")
        assert "tool_that_does_not_exist" in str(result).lower() \
            or "unknown" in result.get("error", "").lower() \
            or "not found" in result.get("error", "").lower()

    def test_tool_with_no_args_does_not_raise(self):
        """Tools called with no args should return a dict, not raise."""
        result = execute_tool("payment_lookup")
        assert isinstance(result, dict)

    def test_tool_with_none_args_does_not_raise(self):
        result = execute_tool("risk_check", payment_id=None)
        assert isinstance(result, dict)

    def test_ticket_creator_no_args_does_not_raise(self):
        result = execute_tool("ticket_creator")
        assert isinstance(result, dict)


# ── Integration: tool results feed into workflow state ────────────────────────

class TestToolWorkflowIntegration:
    """
    Verify that tool results have the structure the runtime expects when it
    updates workflow state.
    """

    def test_payment_lookup_result_has_error_code_for_state(self):
        """The runtime reads error_code to determine fraud vs. card decline."""
        result = execute_tool("payment_lookup", payment_id="PAY-10291")
        assert "error_code" in result

    def test_risk_check_result_has_risk_score_for_routing(self):
        """The runtime uses risk_score to decide if Risk & Compliance must run."""
        result = execute_tool("risk_check", payment_id="PAY-10291")
        assert "risk_score" in result
        assert isinstance(result["risk_score"], (int, float))

    def test_ticket_creator_result_has_ticket_id_for_state(self):
        """ticket_id is stored in extracted_data and referenced in the reply."""
        result = execute_tool("ticket_creator",
                              payment_id="PAY-10291", issue_type="payment_failure")
        assert "ticket_id" in result
        assert result["ticket_id"] is not None
