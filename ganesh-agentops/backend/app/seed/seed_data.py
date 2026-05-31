"""
Default seed data for agents and workflow templates.
Each seed function is idempotent — it runs only when its table is empty.
Safe to call on every startup.
"""

import logging

from app.models.agent import Agent
from app.models.workflow import Workflow

logger = logging.getLogger(__name__)

# ── Seed definitions ─────────────────────────────────────────────────────────

DEFAULT_AGENTS: list[dict] = [
    {
        "name": "Support Intake Agent",
        "role": "Customer Support Intake Specialist",
        "system_prompt": (
            "You are a customer support intake specialist for Ganesh AgentOps, a payment orchestration platform. "
            "Your responsibilities:\n"
            "1. Greet customers professionally and empathetically.\n"
            "2. Gather essential context: transaction ID, date, amount, currency, error message, and merchant name.\n"
            "3. Classify the issue into exactly one category: payment_failure | refund_request | "
            "account_issue | fraud_suspicion | technical_bug | general_inquiry.\n"
            "4. For fraud_suspicion or any mention of legal action: immediately hand off to the "
            "Risk & Compliance Agent without further investigation.\n"
            "5. For payment_failure and refund_request: route to the Payment Investigator Agent.\n"
            "6. Resolve general_inquiry tickets directly using the knowledge base tool.\n"
            "7. Always create a support ticket before closing any conversation.\n\n"
            "Rules: never share internal system details, never promise refund timelines you cannot guarantee, "
            "always confirm the customer's preferred contact channel before closing."
        ),
        "model": "claude-sonnet-4-6",
        "tools": ["ticket_create", "knowledge_base_search", "customer_lookup", "agent_handoff"],
        "channels": ["telegram", "internal"],
        "memory_enabled": True,
        "guardrails": {
            "block_topics": ["competitor_pricing", "internal_system_architecture"],
            "max_response_length_chars": 1200,
            "require_escalation_on": ["legal_threat", "fraud_claim", "data_breach_mention"],
            "pii_handling": "mask_in_logs",
            "tone": "professional_empathetic",
            "prohibited_promises": ["exact_refund_date", "guaranteed_outcome"],
        },
        "limits": {
            "max_steps": 8,
            "max_tokens": 2048,
            "max_cost": 0.05,
            "timeout_seconds": 30,
            "max_concurrent_sessions": 50,
        },
    },
    {
        "name": "Payment Investigator Agent",
        "role": "Payment Investigation Specialist",
        "system_prompt": (
            "You are a senior payment investigation specialist with deep expertise in card networks "
            "(Visa, Mastercard, Amex), ACH, SEPA, and PIX payment rails.\n\n"
            "Workflow:\n"
            "1. Accept a handoff from the Support Intake Agent containing the transaction ID and issue summary.\n"
            "2. Query gateway logs to retrieve the full transaction lifecycle: authorization, capture, "
            "settlement, and any decline codes.\n"
            "3. Identify the failure owner: merchant | acquirer | card_network | issuing_bank | processor.\n"
            "4. Classify the root cause: insufficient_funds | card_declined | network_timeout | "
            "fraud_hold | 3ds_failure | processor_error | duplicate_transaction | "
            "currency_mismatch | expired_card.\n"
            "5. For fraud_hold: immediately escalate to the Risk & Compliance Agent, do not investigate further.\n"
            "6. For all other failures: determine the correct remediation action and prepare a case summary.\n"
            "7. Output a structured investigation report with: root_cause, failure_owner, evidence_refs[], "
            "recommended_action, confidence_score (0-1).\n\n"
            "PII rules: always mask card numbers (show last 4 only), mask bank account numbers, "
            "redact CVV/CVC entirely. Every external API call must be logged for audit."
        ),
        "model": "claude-sonnet-4-6",
        "tools": [
            "transaction_lookup",
            "payment_gateway_query",
            "acquirer_api",
            "fraud_signal_check",
            "decline_code_resolver",
            "report_generator",
        ],
        "channels": ["internal"],
        "memory_enabled": True,
        "guardrails": {
            "pii_masking": True,
            "require_audit_log": True,
            "max_external_api_calls_per_case": 10,
            "require_evidence_before_resolution": True,
            "immutable_case_log": True,
            "disallow_resolution_without_root_cause": True,
        },
        "limits": {
            "max_steps": 20,
            "max_tokens": 4096,
            "max_cost": 0.10,
            "timeout_seconds": 120,
            "max_concurrent_investigations": 10,
            "min_confidence_score_to_auto_resolve": 0.85,
        },
    },
    {
        "name": "Risk & Compliance Agent",
        "role": "Risk and Compliance Analyst",
        "system_prompt": (
            "You are a risk and compliance analyst specializing in financial crime prevention and "
            "regulatory adherence for a global payment processor.\n\n"
            "Responsibilities:\n"
            "1. Perform AML (Anti-Money Laundering) transaction screening using pattern analysis and "
            "rule-based signals.\n"
            "2. Run KYC (Know Your Customer) verification checks when a new or suspicious account is flagged.\n"
            "3. Cross-reference all flagged entities against OFAC, EU Consolidated, and UN Security Council "
            "sanctions lists.\n"
            "4. Compute a composite risk score (0–100) using: transaction velocity, geolocation anomaly, "
            "device fingerprint mismatch, counterparty risk, and historical fraud signals.\n"
            "5. Score-based decision protocol:\n"
            "   - Score >= 80: freeze transaction immediately + require senior analyst approval before release.\n"
            "   - Score 50–79: flag for compliance review within 24 hours.\n"
            "   - Score < 50: clear the transaction, log the decision with full reasoning.\n"
            "6. Draft a Suspicious Activity Report (SAR) whenever a transaction is frozen with score >= 80.\n"
            "7. Every decision must include: risk_score, contributing_factors[], decision, regulatory_basis, "
            "analyst_notes.\n\n"
            "Regulatory frameworks in scope: PCI-DSS v4, GDPR Article 22, EU 5AMLD, FinCEN BSA. "
            "Operate with zero tolerance for incomplete audit trails."
        ),
        "model": "claude-opus-4-8",
        "tools": [
            "aml_screening",
            "kyc_lookup",
            "sanctions_checker",
            "risk_score_engine",
            "sar_draft_generator",
            "transaction_freeze",
            "compliance_db_search",
            "regulatory_lookup",
        ],
        "channels": ["internal"],
        "memory_enabled": True,
        "guardrails": {
            "require_human_approval_above_risk_score": 80,
            "pii_masking": True,
            "immutable_audit_trail": True,
            "block_topics": ["methods_to_evade_detection", "sanctions_circumvention"],
            "regulatory_frameworks": ["PCI-DSS-v4", "GDPR", "EU-5AMLD", "FinCEN-BSA"],
            "decision_logging": "mandatory",
            "sar_auto_draft_threshold": 80,
        },
        "limits": {
            "max_steps": 25,
            "max_tokens": 8192,
            "max_cost": 0.25,
            "timeout_seconds": 300,
            "freeze_threshold_risk_score": 80,
            "review_threshold_risk_score": 50,
            "max_sanctions_list_lookups": 5,
        },
    },
    {
        "name": "Resolution Agent",
        "role": "Customer Resolution and Remediation Specialist",
        "system_prompt": (
            "You are a customer resolution specialist responsible for executing approved remediation actions "
            "and closing support cases with a high customer satisfaction score.\n\n"
            "Workflow:\n"
            "1. Receive an approved investigation summary and resolution plan from the Payment Investigator Agent.\n"
            "2. Match the case to a resolution action:\n"
            "   - payment_failure (processor/merchant error): initiate a payment retry via the correct rail.\n"
            "   - refund_request (approved): initiate refund — original payment method preferred, "
            "bank transfer as fallback.\n"
            "   - sla_breach: apply a compensation credit to the customer's account.\n"
            "   - no_fault_found: notify customer with a clear explanation and close the ticket.\n"
            "3. Refund/compensation > $500 USD equivalent: STOP and request human manager approval before "
            "executing. Never bypass this threshold.\n"
            "4. Send a customer-facing notification in plain, empathetic language — no technical jargon, "
            "no unexplained acronyms.\n"
            "5. Update the support ticket with: resolution_type, amount_processed, execution_timestamp, "
            "and customer_notified=true.\n"
            "6. Generate a post-resolution QA summary for the quality assurance team.\n\n"
            "SLA targets: refunds processed within 72 hours, customer notified within 2 hours of case closure."
        ),
        "model": "claude-sonnet-4-6",
        "tools": [
            "refund_initiator",
            "retry_payment",
            "compensation_credit",
            "ticket_update",
            "email_sender",
            "sms_sender",
            "push_notification",
            "qa_summary_generator",
        ],
        "channels": ["internal", "telegram"],
        "memory_enabled": True,
        "guardrails": {
            "max_auto_refund_usd": 500,
            "require_human_approval_above_usd": 500,
            "block_actions": ["account_closure", "chargeback_bypass", "sanctions_override"],
            "communication_tone": "empathetic_plain_language",
            "refund_sla_hours": 72,
            "customer_notification_sla_hours": 2,
            "prohibited_actions_without_approval": ["bulk_refund", "policy_exception"],
        },
        "limits": {
            "max_steps": 12,
            "max_tokens": 2048,
            "max_cost": 0.05,
            "timeout_seconds": 60,
            "max_refund_attempts": 3,
            "compensation_cap_usd": 200,
        },
    },
]


# ── Sample demo inputs ────────────────────────────────────────────────────────
# Ordered oldest-first so the "Recent Runs" table shows them newest-first.
# Uses the real AgentRuntime (MockLLM, no API key needed) so messages, logs,
# and output_payload are fully populated — the run detail page shows real content.

_DEMO_RUNS: list[dict] = [
    {
        "hours_ago": 3,
        "payment_id": "PAY-77881",
        "country": "CO",
        "message": (
            "Transaction PAY-77881 flagged by risk engine for a customer in Colombia. "
            "Unusual velocity — 8 authorisation attempts in the last 2 hours. "
            "Requires immediate compliance review."
        ),
    },
    {
        "hours_ago": 2,
        "payment_id": "PAY-20455",
        "country": "MX",
        "message": (
            "Payment PAY-20455 declined for a customer in Mexico. "
            "Card shows expired status. Customer is requesting a refund or retry."
        ),
    },
    {
        "hours_ago": 1,
        "payment_id": "PAY-10291",
        "country": "BR",
        "message": (
            "Payment PAY-10291 failed for a customer in Brazil. "
            "Card declined with error CARD_DECLINED. Please investigate and recommend next action."
        ),
    },
]


# ── Seed runner ───────────────────────────────────────────────────────────────

def seed_agents(db=None) -> None:
    """
    Insert DEFAULT_AGENTS into the database.
    No-op if any agents already exist — safe to call on every startup.

    Args:
        db: An existing SQLAlchemy Session. If None, a new session is created
            and closed automatically. Pass an explicit session in tests so the
            seed writes to the same database the test client reads from.
    """
    from app.database import SessionLocal  # local import avoids circular deps at module load

    _owns_session = db is None
    if _owns_session:
        db = SessionLocal()
    try:
        if db.query(Agent).count() > 0:
            return
        for data in DEFAULT_AGENTS:
            db.add(Agent(**data))
        db.commit()
        logger.info("[seed] Inserted %d default agents.", len(DEFAULT_AGENTS))
    finally:
        if _owns_session:
            db.close()


def seed_workflows(db=None) -> None:
    """
    Insert one Workflow record per template as example workflows.
    No-op if any workflows already exist — safe to call on every startup.

    Args:
        db: An existing SQLAlchemy Session. If None, a new session is created
            and closed automatically. Pass an explicit session in tests so the
            seed writes to the same database the test client reads from.
    """
    from app.database import SessionLocal
    from app.seed.workflow_templates import WORKFLOW_TEMPLATES

    _owns_session = db is None
    if _owns_session:
        db = SessionLocal()
    try:
        if db.query(Workflow).count() > 0:
            return
        for tmpl in WORKFLOW_TEMPLATES.values():
            db.add(Workflow(
                name=tmpl["name"],
                description=tmpl["description"],
                nodes=tmpl["nodes"],
                edges=tmpl["edges"],
                template_type=tmpl["template_type"],
            ))
        db.commit()
        logger.info("[seed] Inserted %d workflow templates.", len(WORKFLOW_TEMPLATES))
    finally:
        if _owns_session:
            db.close()


def seed_sample_runs(db=None) -> None:
    """
    Execute 3 historical demo runs (PAY-77881, PAY-20455, PAY-10291) via the real
    AgentRuntime so messages, logs, and output are fully populated.

    Always uses MockLLM regardless of configured API keys — seeded runs are for
    demo purposes only and must not generate real API costs on startup.
    Backdates timestamps so runs appear historical on the dashboard.
    Safe to call on every startup — no-op when any WorkflowRun already exists.
    """
    from datetime import timedelta

    from app.database import SessionLocal
    from app.models.workflow import Workflow
    from app.models.workflow_run import WorkflowRun
    from app.runtime.agent_runtime import AgentRuntime
    from app.runtime.event_bus import bus
    from app.utils import utcnow

    _owns_session = db is None
    if _owns_session:
        db = SessionLocal()
    try:
        if db.query(WorkflowRun).count() > 0:
            return  # already seeded — idempotent

        wf = (
            db.query(Workflow)
            .filter(Workflow.template_type == "payment_failure_investigation")
            .order_by(Workflow.id)
            .first()
        )
        if wf is None:
            logger.warning(
                "[seed] Cannot seed sample runs: "
                "no 'payment_failure_investigation' workflow in DB."
            )
            return

        # Force MockLLM for seeding — clearing keys makes _get_llm() fall through
        # to MockLLM even when real API keys are configured in .env.
        from app.config import settings
        _saved_oai  = settings.OPENAI_API_KEY
        _saved_anth = settings.ANTHROPIC_API_KEY
        settings.OPENAI_API_KEY  = ""
        settings.ANTHROPIC_API_KEY = ""

        try:
            for demo in _DEMO_RUNS:
                input_payload = {
                    "message":    demo["message"],
                    "payment_id": demo["payment_id"],
                    "country":    demo["country"],
                }
                run = WorkflowRun(
                    workflow_id=wf.id,
                    status="pending",
                    input_payload=input_payload,
                )
                db.add(run)
                db.commit()
                db.refresh(run)

                AgentRuntime(db).execute(run, input_payload)

                # Backdate immediately after each run so all three get correct timestamps
                hours = demo["hours_ago"]
                run.started_at   = utcnow() - timedelta(hours=hours)
                run.completed_at = run.started_at + timedelta(seconds=2)
                db.commit()

                # In-memory events for historical runs are not streamed — free them
                bus.clear(run.id)

                logger.info(
                    "[seed] Demo run #%d (%s, %s) → status=%s",
                    run.id,
                    demo["payment_id"],
                    demo["country"],
                    run.status,
                )
        finally:
            settings.OPENAI_API_KEY  = _saved_oai
            settings.ANTHROPIC_API_KEY = _saved_anth
    finally:
        if _owns_session:
            db.close()
