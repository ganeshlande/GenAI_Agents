"""
Static workflow template definitions.

Templates are pure Python dicts — they are NOT stored in the database.
The `GET /api/templates` endpoint serves them directly.
`POST /api/templates/{template_type}/create-workflow` instantiates a real
Workflow DB record from whichever template the caller selects.

Node / edge shapes follow the React Flow (@xyflow/react) schema so the
frontend canvas can render them without any transformation.
"""

from typing import Any

WORKFLOW_TEMPLATES: dict[str, dict[str, Any]] = {

    # ── Template 1 ────────────────────────────────────────────────────────────
    "payment_failure_investigation": {
        "template_type": "payment_failure_investigation",
        "name": "Payment Failure Investigation",
        "description": (
            "End-to-end workflow for investigating a failed payment transaction. "
            "The intake agent collects context and routes to an investigator who queries "
            "gateway logs. Fraud signals escalate to risk/compliance; clean cases go "
            "directly to the resolution agent for remediation and customer notification."
        ),
        "agents": [
            "Support Intake Agent",
            "Payment Investigator Agent",
            "Risk & Compliance Agent",
            "Resolution Agent",
        ],
        "tools": ["payment_lookup", "risk_check", "ticket_creator"],
        "nodes": [
            {
                "id": "node-intake",
                "type": "agentNode",
                "position": {"x": 50, "y": 200},
                "data": {
                    "label": "Support Intake",
                    "agent_name": "Support Intake Agent",
                    "description": "Collect issue details and classify the ticket",
                    "tools": ["ticket_creator", "customer_lookup"],
                    "color": "#3b82f6",
                },
            },
            {
                "id": "node-investigator",
                "type": "agentNode",
                "position": {"x": 380, "y": 200},
                "data": {
                    "label": "Payment Investigator",
                    "agent_name": "Payment Investigator Agent",
                    "description": "Query gateway logs and identify root cause",
                    "tools": ["payment_lookup", "transaction_lookup"],
                    "color": "#8b5cf6",
                },
            },
            {
                "id": "node-risk",
                "type": "agentNode",
                "position": {"x": 710, "y": 60},
                "data": {
                    "label": "Risk & Compliance",
                    "agent_name": "Risk & Compliance Agent",
                    "description": "AML/fraud screening and risk score calculation",
                    "tools": ["risk_check", "aml_screening"],
                    "color": "#ef4444",
                },
            },
            {
                "id": "node-resolution",
                "type": "agentNode",
                "position": {"x": 1040, "y": 200},
                "data": {
                    "label": "Resolution",
                    "agent_name": "Resolution Agent",
                    "description": "Execute approved resolution and notify the customer",
                    "tools": ["ticket_creator", "refund_initiator"],
                    "color": "#22c55e",
                },
            },
        ],
        "edges": [
            {
                "id": "edge-intake-investigator",
                "source": "node-intake",
                "target": "node-investigator",
                "label": "route_payment_issue",
                "animated": True,
                "data": {
                    "condition": "issue_type in ['payment_failure', 'refund_request']",
                    "description": "Payment/refund issues go to the investigator",
                },
            },
            {
                "id": "edge-investigator-risk",
                "source": "node-investigator",
                "target": "node-risk",
                "label": "escalate_fraud",
                "animated": True,
                "style": {"stroke": "#ef4444", "strokeWidth": 2},
                "data": {
                    "condition": "root_cause == 'fraud_hold'",
                    "description": "Fraud signals escalate to Risk & Compliance",
                },
            },
            {
                "id": "edge-investigator-resolution",
                "source": "node-investigator",
                "target": "node-resolution",
                "label": "resolve_non_fraud",
                "animated": True,
                "style": {"stroke": "#22c55e", "strokeWidth": 2},
                "data": {
                    "condition": "root_cause != 'fraud_hold' AND confidence_score >= 0.85",
                    "description": "High-confidence non-fraud cases go directly to resolution",
                },
            },
            {
                "id": "edge-risk-resolution",
                "source": "node-risk",
                "target": "node-resolution",
                "label": "compliance_cleared",
                "animated": True,
                "data": {
                    "condition": "risk_score < 80",
                    "description": "Risk-cleared transactions proceed to resolution",
                },
            },
        ],
    },

    # ── Template 2 ────────────────────────────────────────────────────────────
    "merchant_onboarding_review": {
        "template_type": "merchant_onboarding_review",
        "name": "Merchant Onboarding Review",
        "description": (
            "Parallel review pipeline for new merchant onboarding applications. "
            "The intake agent validates the application and simultaneously triggers "
            "compliance screening (AML/KYC/sanctions) and documentation verification. "
            "Both branches feed into the resolution agent which approves, rejects, or "
            "requests additional information."
        ),
        "agents": [
            "Support Intake Agent",
            "Risk & Compliance Agent",
            "Payment Investigator Agent",
            "Resolution Agent",
        ],
        "tools": ["risk_check", "ticket_creator", "kyc_lookup"],
        "nodes": [
            {
                "id": "node-intake",
                "type": "agentNode",
                "position": {"x": 50, "y": 220},
                "data": {
                    "label": "Application Intake",
                    "agent_name": "Support Intake Agent",
                    "description": "Receive and validate the onboarding application form",
                    "tools": ["ticket_creator", "customer_lookup"],
                    "color": "#3b82f6",
                },
            },
            {
                "id": "node-compliance",
                "type": "agentNode",
                "position": {"x": 380, "y": 80},
                "data": {
                    "label": "Compliance Check",
                    "agent_name": "Risk & Compliance Agent",
                    "description": "AML, KYC verification and sanctions screening",
                    "tools": ["risk_check", "kyc_lookup", "sanctions_checker"],
                    "color": "#ef4444",
                },
            },
            {
                "id": "node-documentation",
                "type": "agentNode",
                "position": {"x": 380, "y": 360},
                "data": {
                    "label": "Document Review",
                    "agent_name": "Payment Investigator Agent",
                    "description": "Verify business registration and bank account details",
                    "tools": ["document_checker", "bank_account_verifier"],
                    "color": "#8b5cf6",
                },
            },
            {
                "id": "node-resolution",
                "type": "agentNode",
                "position": {"x": 710, "y": 220},
                "data": {
                    "label": "Onboarding Decision",
                    "agent_name": "Resolution Agent",
                    "description": "Approve, reject, or request more information",
                    "tools": ["ticket_creator", "email_sender", "push_notification"],
                    "color": "#22c55e",
                },
            },
        ],
        "edges": [
            {
                "id": "edge-intake-compliance",
                "source": "node-intake",
                "target": "node-compliance",
                "label": "start_compliance_check",
                "animated": True,
                "data": {
                    "condition": "application_valid == True",
                    "description": "Trigger parallel compliance screening",
                },
            },
            {
                "id": "edge-intake-documentation",
                "source": "node-intake",
                "target": "node-documentation",
                "label": "start_doc_review",
                "animated": True,
                "data": {
                    "condition": "application_valid == True",
                    "description": "Trigger parallel document verification",
                },
            },
            {
                "id": "edge-compliance-resolution",
                "source": "node-compliance",
                "target": "node-resolution",
                "label": "compliance_complete",
                "animated": True,
                "data": {
                    "condition": "compliance_passed == True",
                    "description": "Compliance result forwarded to decision agent",
                },
            },
            {
                "id": "edge-documentation-resolution",
                "source": "node-documentation",
                "target": "node-resolution",
                "label": "documentation_complete",
                "animated": True,
                "data": {
                    "condition": "docs_verified == True",
                    "description": "Document result forwarded to decision agent",
                },
            },
        ],
    },
}
