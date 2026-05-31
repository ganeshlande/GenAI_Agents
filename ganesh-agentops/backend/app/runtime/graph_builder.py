"""
Builds a LangGraph StateGraph (or fallback) dynamically from a Workflow DB record.

Key design:
  - WorkflowState is a plain dict — works with both LangGraph and the fallback.
  - Each workflow node maps to a closure that knows its agent definition,
    available tools, DB session, and cost tracker.
  - Conditional edges are resolved by inspecting state flags set during execution
    (fraud_detected, risk_score, etc.).
  - The Mock LLM produces deterministic, role-specific responses so the entire
    pipeline works without any API key.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.models.agent import Agent
from app.models.workflow import Workflow
from app.models.workflow_run import WorkflowRun
from app.runtime.cost_tracker import CostTracker
from app.runtime.event_bus import bus
from app.runtime.guardrails import (
    check_guardrails,
    check_output_structure,
    check_step_limit,
    check_tool_allowed,
)
from app.runtime.memory import persist_log, persist_message
from app.tools.registry import execute_tool

try:
    from langgraph.graph import StateGraph, END
    _LANGGRAPH = True
except ImportError:
    from app.runtime.fallback_graph import StateGraph, END  # type: ignore
    _LANGGRAPH = False


# ── Mock LLM ─────────────────────────────────────────────────────────────────

class MockLLM:
    """
    Deterministic LLM. Role-specific responses let the full 4-agent pipeline
    run end-to-end without any paid API key.
    """

    model = "mock"

    def complete(
        self,
        system_prompt: str,
        conversation: list[dict],
        available_tools: list[str],
        state: dict,
    ) -> dict:
        # Truncate to the first sentence (~80 chars) so references to OTHER agent
        # names in the workflow description (e.g. "hand off to the Support Intake
        # Agent") don't accidentally match the wrong dispatch branch.
        role_hint = (system_prompt + " ").lower()[:80]
        input_text = " ".join(m.get("content", "") for m in conversation).lower()
        full_text = input_text + " " + state.get("input_message", "").lower()

        if "investigat" in role_hint:
            result = self._investigator(available_tools, state, full_text)
        elif "risk" in role_hint or "compliance" in role_hint:
            result = self._risk(available_tools, state, full_text)
        elif "resolution" in role_hint or "remediation" in role_hint:
            result = self._resolution(available_tools, state, full_text)
        elif "intake" in role_hint:
            result = self._intake(available_tools, state, full_text)
        else:
            result = self._generic(state, full_text)

        # Estimate tokens from actual content lengths (1 token ≈ 4 chars).
        # This replaces any hardcoded values the role methods may carry.
        input_source = (
            system_prompt + " "
            + " ".join(m.get("content", "") for m in conversation)
        )
        result["input_tokens"]  = self._count_tokens(input_source)
        result["output_tokens"] = self._count_tokens(result.get("content", ""))
        return result

    @staticmethod
    def _count_tokens(text: str) -> int:
        """1 token ≈ 4 characters — the standard BPE approximation."""
        return max(1, len(text) // 4)

    # ── Role responses ────────────────────────────────────────────────────────

    def _intake(self, tools: list[str], state: dict, text: str) -> dict:
        pid = _extract_payment_id(text) or "PAY-UNKNOWN"
        tcs = []
        if any(t in tools for t in ("ticket_creator", "ticket_create")):
            tname = "ticket_creator" if "ticket_creator" in tools else "ticket_create"
            tcs.append({
                "tool": tname,
                "args": {
                    "payment_id": pid,
                    "issue_type": "payment_failure",
                    "description": f"Customer reported failure for payment {pid}. Initial intake logged.",
                    "priority": "high",
                },
            })
        return {
            "content": (
                f"I've received your request regarding payment **{pid}**.\n\n"
                "**Classification:** payment_failure\n"
                "**Action:** Support ticket created. Routing to the Payment Investigation team "
                "for detailed root-cause analysis."
            ),
            "extracted_data_updates": {
                "payment_id": pid,
                "issue_type": "payment_failure",
                "intake_complete": True,
            },
            "tool_calls": tcs,
        }

    def _investigator(self, tools: list[str], state: dict, text: str) -> dict:
        pid = (
            state.get("extracted_data", {}).get("payment_id")
            or _extract_payment_id(text)
            or "PAY-UNKNOWN"
        )
        tcs = []
        lookup_tool = next(
            (t for t in ("payment_lookup", "transaction_lookup") if t in tools), None
        )
        if lookup_tool:
            tcs.append({"tool": lookup_tool, "args": {"payment_id": pid}})

        # PAY-77881: high-risk fraud pattern — mandatory escalation to Risk & Compliance
        if "77881" in pid:
            return {
                "content": (
                    f"**Investigation complete — {pid}**\n\n"
                    "- **Gateway result:** FRAUD_HOLD — blocked by real-time fraud detection\n"
                    "- **Root cause:** Unusual transaction velocity (8 attempts in 120 min)\n"
                    "- **Failure owner:** RISK_ENGINE\n"
                    "- **Fraud signals:** HIGH — velocity anomaly + geo mismatch (Colombia → EU merchant)\n"
                    "- **Confidence:** 0.82\n\n"
                    "⚠️ Fraud signals confirmed. Mandatory escalation to Risk & Compliance."
                ),
                "extracted_data_updates": {
                    "root_cause": "FRAUD_HOLD",
                    "failure_owner": "RISK_ENGINE",
                    "fraud_detected": True,
                    "confidence_score": 0.82,
                    "payment_id": pid,
                },
                "fraud_detected": True,
                "tool_calls": tcs,
            }

        # PAY-20455: card expired — routine decline, no fraud signals
        if "20455" in pid:
            return {
                "content": (
                    f"**Investigation complete — {pid}**\n\n"
                    "- **Gateway result:** CARD_EXPIRED — card validity date exceeded\n"
                    "- **Root cause:** Customer's card expired 12/2024\n"
                    "- **Failure owner:** CUSTOMER\n"
                    "- **Fraud signals:** None — standard expiry decline, no anomaly\n"
                    "- **Confidence:** 0.99\n\n"
                    "No escalation required. Routing to Resolution for customer notification."
                ),
                "extracted_data_updates": {
                    "root_cause": "CARD_EXPIRED",
                    "failure_owner": "CUSTOMER",
                    "fraud_detected": False,
                    "confidence_score": 0.99,
                    "payment_id": pid,
                },
                "fraud_detected": False,
                "tool_calls": tcs,
            }

        # Default (PAY-10291 and generic IDs): card declined by issuing bank
        return {
            "content": (
                f"**Investigation complete — {pid}**\n\n"
                "- **Gateway result:** CARD_DECLINED — issuing bank declined\n"
                "- **Root cause:** Issuing bank restriction (insufficient funds or card block)\n"
                "- **Failure owner:** ISSUING_BANK\n"
                "- **Fraud signals:** None — CARD_DECLINED is not a fraud indicator\n"
                "- **Confidence:** 0.95\n\n"
                "No escalation to Risk & Compliance required. Routing to Resolution."
            ),
            "extracted_data_updates": {
                "root_cause": "CARD_DECLINED",
                "failure_owner": "ISSUING_BANK",
                "fraud_detected": False,
                "confidence_score": 0.95,
                "payment_id": pid,
            },
            "fraud_detected": False,
            "tool_calls": tcs,
        }

    def _risk(self, tools: list[str], state: dict, text: str) -> dict:
        pid = state.get("extracted_data", {}).get("payment_id", "UNKNOWN")
        tcs = []
        risk_tool = next(
            (t for t in ("risk_check", "aml_screening") if t in tools), None
        )
        if risk_tool:
            tcs.append({"tool": risk_tool, "args": {"payment_id": pid}})

        # Elevated risk path — entered when investigator set fraud_detected=True
        fraud_in_state = state.get("fraud_detected") or state.get("extracted_data", {}).get("fraud_detected")
        if fraud_in_state or "77881" in pid:
            return {
                "content": (
                    f"**Risk Assessment — {pid} — CRITICAL ESCALATION**\n\n"
                    "- **Risk score:** 87 / 100 (CRITICAL)\n"
                    "- **AML flags:** Velocity anomaly, geo mismatch\n"
                    "- **Sanctions:** Negative (OFAC · EU · UN)\n"
                    "- **Velocity anomaly:** YES — 8 attempts in 120 minutes\n"
                    "- **Decision:** HOLD — transaction frozen pending manual review\n"
                    "- **SAR drafted:** Yes — compliance team notified\n\n"
                    "Transaction blocked. Senior compliance analyst assigned. Review SLA: 24 hours."
                ),
                "extracted_data_updates": {
                    "risk_score": 87,
                    "risk_level": "critical",
                    "compliance_cleared": False,
                    "requires_manual_review": True,
                    "sar_filed": True,
                },
                "risk_score": 87,
                "tool_calls": tcs,
            }

        # Standard low-risk path
        return {
            "content": (
                f"**Risk Assessment — {pid}**\n\n"
                "- **Risk score:** 28 / 100 (LOW)\n"
                "- **AML flags:** None\n"
                "- **Sanctions:** Negative (OFAC · EU · UN)\n"
                "- **Velocity anomaly:** No\n"
                "- **Decision:** APPROVED — no compliance concerns\n\n"
                "Forwarding to Resolution for customer communication."
            ),
            "extracted_data_updates": {
                "risk_score": 28,
                "risk_level": "low",
                "compliance_cleared": True,
            },
            "risk_score": 28,
            "tool_calls": tcs,
        }

    def _resolution(self, tools: list[str], state: dict, text: str) -> dict:
        data = state.get("extracted_data", {})
        pid = data.get("payment_id", "UNKNOWN")
        root = data.get("root_cause", "CARD_DECLINED")
        fraud_in_state = state.get("fraud_detected") or data.get("fraud_detected")
        tcs = []
        ticket_tool = next((t for t in tools if "ticket" in t), None)

        # Fraud hold path — transaction frozen, pending compliance review
        if fraud_in_state or root == "FRAUD_HOLD":
            if ticket_tool:
                tcs.append({
                    "tool": ticket_tool,
                    "args": {
                        "payment_id": pid,
                        "issue_type": "fraud_hold_review",
                        "description": (
                            f"Transaction {pid} frozen due to fraud signals. "
                            "Pending compliance team review."
                        ),
                        "priority": "critical",
                    },
                })
            return {
                "content": (
                    f"## Resolution Summary — {pid}\n\n"
                    "**Root cause:** Fraud Hold\n"
                    "**Action taken:** Transaction frozen. SAR filed. Senior compliance analyst notified.\n"
                    "**Customer communication:** Account temporarily restricted pending security review. "
                    "Customer will be contacted within 24 hours via registered email.\n"
                    "**SLA:** Compliance review within 24 h · Customer notification within 2 h.\n"
                    "**Status:** UNDER REVIEW — awaiting compliance approval."
                ),
                "extracted_data_updates": {
                    "resolution_complete": True,
                    "guidance": "Transaction frozen — compliance review in progress",
                    "requires_manual_review": True,
                },
                "tool_calls": tcs,
                "is_final": True,
            }

        # Card expired path — advise customer to update card
        if root == "CARD_EXPIRED":
            if ticket_tool:
                tcs.append({
                    "tool": ticket_tool,
                    "args": {
                        "payment_id": pid,
                        "issue_type": "card_expired_notification",
                        "description": (
                            f"Payment {pid} declined due to expired card. "
                            "Customer notified to update their card details."
                        ),
                        "priority": "medium",
                    },
                })
            return {
                "content": (
                    f"## Resolution Summary — {pid}\n\n"
                    "**Root cause:** Card Expired\n"
                    "**Action taken:** Customer notified to update their card details.\n"
                    "**Customer guidance:** Please update your card in Account Settings "
                    "or contact your bank to activate your replacement card, then retry the payment.\n"
                    "**SLA:** Customer notification within 2 h · Retry window open for 7 days.\n"
                    "**Status:** RESOLVED — awaiting customer card update."
                ),
                "extracted_data_updates": {
                    "resolution_complete": True,
                    "guidance": "Update card details and retry payment",
                },
                "tool_calls": tcs,
                "is_final": True,
            }

        # Default (CARD_DECLINED): advise customer to contact issuing bank
        root_display = root.replace("_", " ").title()
        if ticket_tool:
            tcs.append({
                "tool": ticket_tool,
                "args": {
                    "payment_id": pid,
                    "issue_type": "payment_failure_resolved",
                    "description": (
                        f"Payment {pid} failed due to {root_display}. "
                        "Customer advised to contact their bank or use an alternative payment method."
                    ),
                    "priority": "medium",
                },
            })
        return {
            "content": (
                f"## Resolution Summary — {pid}\n\n"
                f"**Root cause:** {root_display}\n"
                "**Action taken:** Support ticket created and queued for customer notification.\n"
                "**Customer guidance:** Please contact your issuing bank to resolve the card "
                "restriction, or complete the purchase using PIX or bank transfer.\n"
                "**SLA:** Customer notification within 2 hours · Resolution within 72 hours.\n"
                "**Status:** RESOLVED"
            ),
            "extracted_data_updates": {
                "resolution_complete": True,
                "guidance": "Contact issuing bank or use alternative payment method",
            },
            "tool_calls": tcs,
            "is_final": True,
        }

    def _generic(self, state: dict, text: str) -> dict:
        return {
            "content": f"Processing complete. Input received: {text[:120]}",
            "extracted_data_updates": {},
            "tool_calls": [],
        }


def _extract_payment_id(text: str) -> str | None:
    m = re.search(r"\bPAY-\d+\b", text, re.IGNORECASE)
    return m.group(0).upper() if m else None


# ── Real-LLM adapters ─────────────────────────────────────────────────────────
# Both adapt a LangChain chat model to the same .complete() interface used by
# the agent node, so the runtime never needs to know which provider is active.

class _OAIAdapter:
    """Thin wrapper around ChatOpenAI that speaks the internal LLM protocol."""

    def __init__(self, client: Any, model_name: str) -> None:
        self._c = client
        self.model = model_name

    def complete(
        self,
        system_prompt: str,
        conversation: list[dict],
        available_tools: list[str],
        state: dict,
    ) -> dict:
        from langchain_core.messages import HumanMessage, SystemMessage
        msgs = [SystemMessage(content=system_prompt)]
        for m in conversation:
            msgs.append(HumanMessage(content=m.get("content", "")))
        r = self._c.invoke(msgs)
        usage = getattr(r, "usage_metadata", {}) or {}
        return {
            "content": r.content,
            "extracted_data_updates": {},
            "tool_calls": [],
            "input_tokens": usage.get("input_tokens", 500),
            "output_tokens": usage.get("output_tokens", 200),
        }


class _AnthropicAdapter:
    """Thin wrapper around ChatAnthropic that speaks the internal LLM protocol."""

    def __init__(self, client: Any, model_name: str) -> None:
        self._c = client
        self.model = model_name

    def complete(
        self,
        system_prompt: str,
        conversation: list[dict],
        available_tools: list[str],
        state: dict,
    ) -> dict:
        from langchain_core.messages import HumanMessage, SystemMessage
        msgs = [SystemMessage(content=system_prompt)]
        for m in conversation:
            msgs.append(HumanMessage(content=m.get("content", "")))
        r = self._c.invoke(msgs)
        usage = getattr(r, "usage_metadata", {}) or {}
        return {
            "content": r.content,
            "extracted_data_updates": {},
            "tool_calls": [],
            "input_tokens": usage.get("input_tokens", 500),
            "output_tokens": usage.get("output_tokens", 200),
        }


def _get_llm(model: str) -> Any:
    """
    Return a live LLM adapter when an API key is configured, otherwise MockLLM.
    Priority: OpenAI → Anthropic → MockLLM.
    """
    from app.config import settings

    if settings.OPENAI_API_KEY:
        try:
            from langchain_openai import ChatOpenAI
            logger.debug("LLM: using OpenAI gpt-4o-mini")
            return _OAIAdapter(
                ChatOpenAI(model="gpt-4o-mini", api_key=settings.OPENAI_API_KEY),
                "gpt-4o-mini",
            )
        except ImportError:
            logger.debug("langchain_openai not installed — skipping OpenAI")

    if settings.ANTHROPIC_API_KEY:
        try:
            from langchain_anthropic import ChatAnthropic
            logger.debug("LLM: using Anthropic %s", model)
            return _AnthropicAdapter(
                ChatAnthropic(model=model, api_key=settings.ANTHROPIC_API_KEY),
                model,
            )
        except ImportError:
            logger.debug("langchain_anthropic not installed — skipping Anthropic")

    logger.debug("LLM: no API key found — using MockLLM (deterministic demo responses)")
    return MockLLM()


# ── Agent node factory ────────────────────────────────────────────────────────

def _make_agent_node(
    node_id: str,
    agent_info: dict,
    db: Session,
    cost_tracker: CostTracker,
):
    """
    Return a graph-node callable for the given agent.
    All dependencies are captured in the closure.
    """

    def node_fn(state: dict) -> dict:
        agent_obj: Agent | None = agent_info["agent"]
        agent_name: str = agent_info["agent_name"]
        run_id: int = state["run_id"]

        # ── Resolve agent config ──────────────────────────────────────────────
        system_prompt = (agent_obj.system_prompt if agent_obj else "") or f"You are {agent_name}."
        model         = (agent_obj.model          if agent_obj else "mock") or "mock"
        guardrail_cfg = (agent_obj.guardrails      if agent_obj else {}) or {}
        limits_cfg    = (agent_obj.limits          if agent_obj else {}) or {}
        agent_tools   = list(agent_obj.tools or []) if agent_obj else []
        # Merge node-level tool list with agent-level tool list (node takes priority)
        all_tools = list(dict.fromkeys(agent_info["tools"] + agent_tools))

        # ── Guardrail layer 1: step limit ─────────────────────────────────────
        # Track how many times this agent has executed in this run
        agent_steps = dict(state.get("agent_steps", {}))
        current_step = agent_steps.get(agent_name, 0) + 1
        agent_steps[agent_name] = current_step

        # Support both "max_steps" (canonical) and "max_iterations" (legacy alias).
        # Use explicit key check so that max_steps=0 is honoured (not treated as falsy).
        max_steps = (
            limits_cfg["max_steps"]
            if "max_steps" in limits_cfg
            else limits_cfg.get("max_iterations")
        )
        step_check = check_step_limit(current_step, max_steps)
        if not step_check.allowed:
            persist_log(db, run_id, "warning", "step_limit_exceeded",
                        f"Agent '{agent_name}' step limit exceeded",
                        {"agent": agent_name, "step": current_step,
                         "max_steps": max_steps, "reason": step_check.reason})
            bus.publish(run_id, "step_limit_exceeded", step_check.reason,
                        sender_agent=agent_name,
                        metadata={"step": current_step, "max_steps": max_steps})
            return {
                "agent_steps": agent_steps,
                "final_output": f"[STEP LIMIT] {step_check.reason}",
            }

        persist_log(db, run_id, "info", "agent_start",
                    f"Agent '{agent_name}' started (step {current_step})",
                    {"node_id": node_id, "model": model, "tools": all_tools,
                     "step": current_step, "max_steps": max_steps,
                     "langgraph": _LANGGRAPH})
        bus.publish(run_id, "agent_start",
                    f"Agent '{agent_name}' starting",
                    sender_agent=agent_name,
                    metadata={"node_id": node_id, "model": model,
                              "tools": all_tools, "step": current_step})

        # ── Build conversation context ────────────────────────────────────────
        conversation: list[dict] = [{"role": "user", "content": state.get("input_message", "")}]
        for prev in state.get("messages", []):
            if prev.get("agent") != agent_name:
                conversation.append({
                    "role": "assistant",
                    "content": f"[{prev['agent']}]: {prev['content']}",
                })

        # ── LLM call ──────────────────────────────────────────────────────────
        llm = _get_llm(model)
        llm_out = llm.complete(
            system_prompt=system_prompt,
            conversation=conversation,
            available_tools=all_tools,
            state=state,
        )

        raw_content:   str = llm_out.get("content", "")
        input_tokens:  int = llm_out.get("input_tokens", 0)
        output_tokens: int = llm_out.get("output_tokens", 0)
        is_final:     bool = bool(llm_out.get("is_final", False))

        # ── Guardrail layer 2: output content ─────────────────────────────────
        gr = check_guardrails(guardrail_cfg, raw_content)
        if not gr.allowed:
            raw_content = f"[GUARDRAIL BLOCKED] {gr.reason}"
            persist_log(db, run_id, "warning", "guardrail_blocked",
                        f"Agent '{agent_name}' response blocked by content guardrail",
                        {"agent": agent_name, "reason": gr.reason})
            bus.publish(run_id, "guardrail_blocked",
                        f"Content guardrail blocked response: {gr.reason}",
                        sender_agent=agent_name,
                        metadata={"reason": gr.reason, "layer": "content"})
            is_final = False  # blocked response must not close the workflow
        else:
            raw_content = gr.final_content or raw_content

        # ── Guardrail layer 3: final output structure ─────────────────────────
        struct_check = check_output_structure(raw_content, is_final)
        if not struct_check.allowed:
            persist_log(db, run_id, "warning", "guardrail_blocked",
                        f"Agent '{agent_name}' final response failed structure check",
                        {"agent": agent_name, "reason": struct_check.reason})
            bus.publish(run_id, "guardrail_blocked",
                        f"Final output structure check failed: {struct_check.reason}",
                        sender_agent=agent_name,
                        metadata={"reason": struct_check.reason, "layer": "structure"})
            # Append the reason to the content so the evaluator can see it,
            # but do not set is_final — let the workflow continue if possible.
            raw_content = raw_content + f"\n\n[STRUCTURE CHECK] {struct_check.reason}"
        else:
            raw_content = struct_check.final_content or raw_content

        # ── Execute tool calls (with allowlist validation) ────────────────────
        tool_results: list[dict] = []
        for tc in llm_out.get("tool_calls", []):
            tname = tc.get("tool", "")
            targs = tc.get("args", {})

            # Guardrail layer 4: tool allowlist
            tool_check = check_tool_allowed(tname, all_tools)
            if not tool_check.allowed:
                persist_log(db, run_id, "warning", "tool_blocked",
                            f"Agent '{agent_name}' tried to call blocked tool '{tname}'",
                            {"agent": agent_name, "tool": tname,
                             "reason": tool_check.reason, "allowed": all_tools})
                bus.publish(run_id, "tool_blocked",
                            f"Tool '{tname}' blocked — not in agent's allowed list",
                            sender_agent=agent_name,
                            metadata={"tool": tname, "reason": tool_check.reason,
                                      "allowed_tools": all_tools})
                continue  # skip this tool call

            persist_log(db, run_id, "info", "tool_call",
                        f"Agent '{agent_name}' → tool '{tname}'",
                        {"tool": tname, "args": targs})
            bus.publish(run_id, "tool_call",
                        f"Calling tool '{tname}'",
                        sender_agent=agent_name,
                        metadata={"tool": tname, "args": targs})
            result = execute_tool(tname, **targs)
            tool_results.append({"tool": tname, "args": targs, "result": result})
            persist_log(db, run_id, "info", "tool_result",
                        f"Tool '{tname}' returned",
                        {"tool": tname, "result": result})
            bus.publish(run_id, "tool_result",
                        f"Tool '{tname}' returned",
                        sender_agent=agent_name,
                        metadata={"tool": tname, "result": result})

        # ── Cost tracking ─────────────────────────────────────────────────────
        cost_tracker.track(
            agent_name,
            llm.model if hasattr(llm, "model") else model,
            input_tokens,
            output_tokens,
        )

        # ── Warn on token / cost limit breaches (do not stop) ─────────────────
        max_tokens = limits_cfg.get("max_tokens")
        if max_tokens:
            cumulative = (
                state.get("total_input_tokens", 0)
                + state.get("total_output_tokens", 0)
                + input_tokens + output_tokens
            )
            if cumulative > max_tokens:
                persist_log(db, run_id, "warning", "token_limit_warning",
                            f"Agent '{agent_name}' cumulative tokens {cumulative} "
                            f"exceed max_tokens {max_tokens}",
                            {"agent": agent_name, "cumulative_tokens": cumulative,
                             "max_tokens": max_tokens})

        # ── Persist message and completion events ─────────────────────────────
        persist_message(db, run_id,
                        sender_agent=agent_name, receiver_agent=None,
                        content=raw_content, message_type="text")
        bus.publish(run_id, "agent_message", raw_content,
                    sender_agent=agent_name,
                    metadata={"node_id": node_id, "word_count": len(raw_content.split())})

        persist_log(db, run_id, "info", "agent_end",
                    f"Agent '{agent_name}' completed",
                    {"in_tokens": input_tokens, "out_tokens": output_tokens,
                     "step": current_step})
        bus.publish(run_id, "agent_end",
                    f"Agent '{agent_name}' completed — "
                    f"{input_tokens}in/{output_tokens}out tokens",
                    sender_agent=agent_name,
                    metadata={"in_tokens": input_tokens, "out_tokens": output_tokens,
                              "step": current_step})

        # ── Build state updates ───────────────────────────────────────────────
        extracted = dict(state.get("extracted_data", {}))
        extracted.update(llm_out.get("extracted_data_updates", {}))

        updates: dict = {
            "messages":    [{"agent": agent_name, "content": raw_content, "node_id": node_id}],
            "tool_results": tool_results,
            "agent_outputs": {**state.get("agent_outputs", {}), agent_name: raw_content},
            "extracted_data": extracted,
            "agent_steps": agent_steps,
            "total_input_tokens":  state.get("total_input_tokens", 0)  + input_tokens,
            "total_output_tokens": state.get("total_output_tokens", 0) + output_tokens,
        }

        # Propagate routing flags set by the LLM
        for flag in ("fraud_detected", "risk_score"):
            for src in (llm_out, llm_out.get("extracted_data_updates", {})):
                if flag in src:
                    updates[flag] = src[flag]

        # Last agent to produce content with is_final=True wins final_output;
        # fall back to the first agent's output if no agent sets is_final
        if is_final or not state.get("final_output"):
            updates["final_output"] = raw_content

        return updates

    node_fn.__name__ = f"agent_node_{node_id}"
    return node_fn


# ── Routing ───────────────────────────────────────────────────────────────────

def _make_routing_fn(outgoing_edges: list[dict]):
    """
    Return a routing function for nodes with multiple outgoing edges.
    Labels from the workflow template edge definitions are matched against
    well-known state flags.
    """
    labels = [e.get("label", "") for e in outgoing_edges]

    def route(state: dict) -> str:
        # Fraud escalation
        if "escalate_fraud" in labels and state.get("fraud_detected"):
            return "escalate_fraud"
        # High-risk threshold
        if "high_risk" in labels and state.get("risk_score", 0) >= 80:
            return "high_risk"
        # Default: first non-escalation label
        for lbl in labels:
            if lbl not in ("escalate_fraud", "high_risk"):
                return lbl
        return labels[0]

    return route


# ── Graph builder ─────────────────────────────────────────────────────────────

def build_graph(
    workflow: Workflow,
    run: WorkflowRun,
    db: Session,
    cost_tracker: CostTracker,
):
    """
    Compile a StateGraph from the Workflow's nodes and edges.
    Logs which implementation is active (langgraph vs fallback).
    """
    persist_log(db, run.id, "info", "graph_build",
                f"Building graph for '{workflow.name}' "
                f"({'langgraph' if _LANGGRAPH else 'fallback'} engine)",
                {"nodes": len(workflow.nodes or []),
                 "edges": len(workflow.edges or []),
                 "langgraph_installed": _LANGGRAPH})

    if not workflow.nodes:
        raise ValueError(f"Workflow '{workflow.name}' has no nodes to execute")

    # Resolve agent DB records for every node
    agent_info_map: dict[str, dict] = {}
    ordered_ids: list[str] = []
    for node in workflow.nodes:
        nid = node["id"]
        aname = node.get("data", {}).get("agent_name") or node.get("data", {}).get("label", f"agent-{nid}")
        aobj = db.query(Agent).filter(Agent.name == aname).first()
        agent_info_map[nid] = {
            "node_id": nid,
            "agent_name": aname,
            "agent": aobj,
            "tools": node.get("data", {}).get("tools", []),
        }
        ordered_ids.append(nid)

    # Parse edges into adjacency list
    edges_by_src: dict[str, list[dict]] = {}
    for edge in (workflow.edges or []):
        src = edge.get("source", "")
        if src:
            edges_by_src.setdefault(src, []).append(edge)

    # Build the graph
    graph = StateGraph(dict)

    for nid in ordered_ids:
        graph.add_node(nid, _make_agent_node(nid, agent_info_map[nid], db, cost_tracker))

    graph.set_entry_point(ordered_ids[0])

    for nid in ordered_ids:
        outgoing = edges_by_src.get(nid, [])
        if not outgoing:
            graph.add_edge(nid, END)
        elif len(outgoing) == 1:
            graph.add_edge(nid, outgoing[0]["target"])
        else:
            graph.add_conditional_edges(
                nid,
                _make_routing_fn(outgoing),
                {e.get("label", ""): e["target"] for e in outgoing},
            )

    return graph.compile()
