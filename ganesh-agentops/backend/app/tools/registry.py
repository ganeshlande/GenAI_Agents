"""
Tool registry: callable implementations for every tool name an agent can use.
All tools have deterministic mock implementations — no external APIs required.
"""

import hashlib
from datetime import datetime, timezone
from typing import Any, Callable


def _h(text: str) -> int:
    return int(hashlib.md5(text.encode()).hexdigest(), 16)


# ── Tool implementations ─────────────────────────────────────────────────────

def payment_lookup(payment_id: str = "", **_) -> dict:
    """Query gateway logs for a transaction."""
    pid = str(payment_id).upper()

    # PAY-10291: Brazil CARD_DECLINED demo (primary demo path)
    if "10291" in pid:
        return {
            "payment_id": pid,
            "status": "failed",
            "error_code": "CARD_DECLINED",
            "error_message": "Transaction declined by issuing bank",
            "amount": 250.00,
            "currency": "BRL",
            "merchant": "TechStore Brasil",
            "gateway": "PayBR_v2",
            "acquirer": "Banco Inter",
            "failure_owner": "ISSUING_BANK",
            "timestamp": "2024-01-15T14:23:00Z",
            "customer_country": "BR",
            "card_last4": "4291",
        }

    # PAY-20455: Mexico CARD_EXPIRED demo
    if "20455" in pid:
        return {
            "payment_id": pid,
            "status": "failed",
            "error_code": "CARD_EXPIRED",
            "error_message": "Card validity date has elapsed",
            "amount": 1_250.00,
            "currency": "MXN",
            "merchant": "Marketplace México SA",
            "gateway": "PayMX_v3",
            "acquirer": "Banamex",
            "failure_owner": "CUSTOMER",
            "timestamp": "2024-01-15T11:47:00Z",
            "customer_country": "MX",
            "card_last4": "0455",
        }

    # PAY-77881: Colombia FRAUD_HOLD demo (escalates to Risk & Compliance)
    if "77881" in pid:
        return {
            "payment_id": pid,
            "status": "failed",
            "error_code": "FRAUD_HOLD",
            "error_message": "Transaction blocked by real-time fraud detection",
            "amount": 4_800.00,
            "currency": "COP",
            "merchant": "ElectroStore Colombia SAS",
            "gateway": "PayCO_v2",
            "acquirer": "Bancolombia",
            "failure_owner": "RISK_ENGINE",
            "timestamp": "2024-01-15T09:15:00Z",
            "customer_country": "CO",
            "card_last4": "7881",
            "velocity_anomaly": True,
            "attempts_last_2h": 8,
        }

    idx = _h(pid) % 3
    codes = ["INSUFFICIENT_FUNDS", "NETWORK_TIMEOUT", "CARD_EXPIRED"]
    return {
        "payment_id": pid,
        "status": "failed",
        "error_code": codes[idx],
        "amount": round((_h(pid) % 50000) / 100, 2),
        "currency": "USD",
        "failure_owner": "ACQUIRER",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def risk_check(payment_id: str = "", amount: float = 0.0, **_) -> dict:
    """AML / fraud risk assessment."""
    pid = str(payment_id).upper()

    # PAY-77881: high-risk fraud pattern
    if "77881" in pid:
        return {
            "payment_id": pid,
            "risk_score": 87,
            "risk_level": "critical",
            "aml_flags": ["velocity_anomaly", "geo_mismatch"],
            "sanctions_match": False,
            "velocity_anomaly": True,
            "geo_anomaly": True,
            "attempts_last_2h": 8,
            "recommendation": "freeze",
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
        }

    return {
        "payment_id": pid,
        "risk_score": 28,
        "risk_level": "low",
        "aml_flags": [],
        "sanctions_match": False,
        "velocity_anomaly": False,
        "geo_anomaly": False,
        "recommendation": "approve",
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
    }


def ticket_creator(
    payment_id: str = "",
    issue_type: str = "payment_failure",
    description: str = "",
    priority: str = "medium",
    **_,
) -> dict:
    """Create a support ticket."""
    ticket_id = f"TKT-{abs(_h(str(payment_id))) % 90000 + 10000}"
    return {
        "ticket_id": ticket_id,
        "payment_id": str(payment_id).upper(),
        "issue_type": issue_type,
        "status": "open",
        "priority": priority,
        "description": description,
        "assigned_to": "support-team",
        "sla_hours": 24,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def knowledge_base_search(query: str = "", **_) -> dict:
    return {
        "query": query,
        "results": [
            "Payments typically settle in 1–3 business days.",
            "Card declines should be escalated to the issuing bank.",
            "Refunds are processed within 5–7 business days.",
        ],
    }


def customer_lookup(customer_id: str = "", payment_id: str = "", **_) -> dict:
    return {
        "customer_id": customer_id or "CUST-9821",
        "name": "Ana Lima",
        "email": "ana.lima@example.com",
        "tier": "standard",
        "country": "BR",
        "payment_history": {"total": 12, "failed": 1},
    }


def _noop_refund(payment_id: str = "", amount: float = 0.0, **_) -> dict:
    return {
        "refund_id": f"REF-{abs(_h(str(payment_id))) % 9999:05d}",
        "payment_id": str(payment_id).upper(),
        "amount": amount,
        "status": "initiated",
    }


# ── Registry ─────────────────────────────────────────────────────────────────

TOOL_REGISTRY: dict[str, Callable] = {
    # Core tools
    "payment_lookup":        payment_lookup,
    "transaction_lookup":    payment_lookup,   # alias
    "risk_check":            risk_check,
    "aml_screening":         risk_check,       # alias
    "ticket_creator":        ticket_creator,
    "ticket_create":         ticket_creator,   # alias
    "ticket_update":         ticket_creator,   # alias (mock)
    "knowledge_base_search": knowledge_base_search,
    "customer_lookup":       customer_lookup,
    "refund_initiator":      _noop_refund,
    "retry_payment":         lambda payment_id="", **_: {"status": "retry_queued", "payment_id": payment_id},
    "email_sender":          lambda recipient="", subject="", body="", **_: {"sent": True, "recipient": recipient},
    "sms_sender":            lambda recipient="", message="", **_: {"sent": True},
    "push_notification":     lambda user_id="", message="", **_: {"sent": True},
    "sanctions_checker":     lambda payment_id="", **_: {"sanctions_match": False, "lists_checked": ["OFAC", "EU", "UN"]},
    "kyc_lookup":            lambda customer_id="", **_: {"kyc_status": "verified", "risk_band": "low"},
    "report_generator":      lambda **_: {"report_id": "RPT-001", "status": "generated"},
    "bank_account_verifier": lambda account_id="", **_: {"verified": True, "bank": "Banco do Brasil"},
    "document_checker":      lambda **_: {"documents_complete": True, "missing": []},
    "fraud_signal_check":    risk_check,
    "acquirer_api":          payment_lookup,
    "decline_code_resolver": lambda code="", **_: {"code": code, "reason": "Bank declined", "action": "contact_bank"},
}


def execute_tool(tool_name: str, **kwargs) -> dict:
    """Execute a registered tool by name. Returns an error dict if unknown."""
    fn = TOOL_REGISTRY.get(tool_name)
    if fn is None:
        return {
            "error": f"Tool '{tool_name}' not in registry",
            "available_tools": list(TOOL_REGISTRY.keys()),
        }
    try:
        return fn(**kwargs)
    except Exception as exc:
        return {"error": str(exc), "tool": tool_name}
