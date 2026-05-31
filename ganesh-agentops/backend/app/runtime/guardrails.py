"""
Agent guardrail enforcement.

Three layers, checked in order during each agent step:

1. check_step_limit    — enforces max_steps from agent limits config
2. check_tool_allowed  — validates tool names against the agent's allowlist
3. check_guardrails    — validates LLM output content against guardrail rules
4. check_output_structure — validates that final responses have minimum structure
"""

from dataclasses import dataclass

# Minimum character length accepted as a "structured" final response
_MIN_FINAL_RESPONSE_CHARS = 50


@dataclass
class GuardrailResult:
    allowed: bool
    reason: str | None = None
    final_content: str | None = None  # may be truncated version of original


# ── 1. Step limit ─────────────────────────────────────────────────────────────

def check_step_limit(current_steps: int, max_steps: int | None) -> GuardrailResult:
    """
    Block the agent from executing if it has exceeded its max_steps limit.

    ``current_steps`` is the step count AFTER incrementing (i.e. this call is
    step N). Pass ``None`` for ``max_steps`` to disable the check.
    """
    if max_steps is not None and current_steps > max_steps:
        return GuardrailResult(
            allowed=False,
            reason=(
                f"Agent exceeded max_steps limit "
                f"(step {current_steps} > max {max_steps})"
            ),
        )
    return GuardrailResult(allowed=True)


# ── 2. Tool allowlist ─────────────────────────────────────────────────────────

def check_tool_allowed(tool_name: str, allowed_tools: list[str]) -> GuardrailResult:
    """
    Block a tool call if the tool is not in the agent's allowed list.

    When ``allowed_tools`` is empty the check is skipped (no restriction
    configured), which preserves backward compatibility with agents that have
    no explicit tool list.
    """
    if not allowed_tools:
        return GuardrailResult(allowed=True)
    if tool_name not in allowed_tools:
        return GuardrailResult(
            allowed=False,
            reason=(
                f"Tool '{tool_name}' is not in this agent's allowed list. "
                f"Allowed: {allowed_tools}"
            ),
        )
    return GuardrailResult(allowed=True)


# ── 3. Output content ─────────────────────────────────────────────────────────

def check_guardrails(guardrail_config: dict, content: str) -> GuardrailResult:
    """
    Validate LLM output ``content`` against the rules in ``guardrail_config``.

    Supported keys:
      block_topics              list[str]  — block if any topic appears in content
      block_actions             list[str]  — block if any action phrase appears
      prohibited_promises       list[str]  — block if any promise phrase appears
      max_response_length_chars int        — truncate (not block) if exceeded

    Returns GuardrailResult(allowed=True) when all checks pass.
    Sets final_content to a truncated version when a length rule fires.
    """
    if not guardrail_config:
        return GuardrailResult(allowed=True, final_content=content)

    low = content.lower()

    for topic in guardrail_config.get("block_topics", []):
        if topic.lower().replace("_", " ") in low:
            return GuardrailResult(
                allowed=False,
                reason=f"Content blocked: mentions restricted topic '{topic}'",
            )

    for action in guardrail_config.get("block_actions", []):
        if action.lower().replace("_", " ") in low:
            return GuardrailResult(
                allowed=False,
                reason=f"Blocked action '{action}' detected in response",
            )

    for promise in guardrail_config.get("prohibited_promises", []):
        if promise.lower().replace("_", " ") in low:
            return GuardrailResult(
                allowed=False,
                reason=f"Prohibited promise '{promise}' detected",
            )

    max_len = guardrail_config.get("max_response_length_chars")
    if max_len and isinstance(max_len, int) and len(content) > max_len:
        truncated = content[:max_len].rstrip() + " … [truncated by guardrail]"
        return GuardrailResult(allowed=True, final_content=truncated)

    return GuardrailResult(allowed=True, final_content=content)


# ── 4. Final output structure ─────────────────────────────────────────────────

def check_output_structure(content: str, is_final: bool) -> GuardrailResult:
    """
    For responses marked as final (``is_final=True``), reject content that is
    shorter than ``_MIN_FINAL_RESPONSE_CHARS`` characters.

    This catches cases where an agent emits an empty or degenerate output and
    tries to close the workflow with it.  Non-final responses are always allowed.
    """
    if not is_final:
        return GuardrailResult(allowed=True, final_content=content)
    if len(content.strip()) < _MIN_FINAL_RESPONSE_CHARS:
        return GuardrailResult(
            allowed=False,
            reason=(
                f"Final response is too short ({len(content.strip())} chars). "
                f"Minimum required: {_MIN_FINAL_RESPONSE_CHARS} chars."
            ),
        )
    return GuardrailResult(allowed=True, final_content=content)
