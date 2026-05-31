"""
Token usage and cost tracking for agent runs.

Token counts come from two sources:
- MockLLM: estimated via content-length heuristic (1 token ≈ 4 chars).  Cost is $0.00
  because no real API is called.
- Real LLMs (OpenAI / Anthropic): exact counts from provider usage_metadata; cost is
  calculated from the pricing table below.
"""

from dataclasses import dataclass, field

# Per-million-token prices (USD, approximate as of 2025-05)
_PRICING: dict[str, dict[str, float]] = {
    "claude-opus-4-8":   {"input": 15.00, "output": 75.00},
    "claude-sonnet-4-6": {"input":  3.00, "output": 15.00},
    "claude-haiku-4-5":  {"input":  0.25, "output":  1.25},
    "gpt-4o":            {"input":  5.00, "output": 15.00},
    "gpt-4o-mini":       {"input":  0.15, "output":  0.60},
    # Mock model has no API cost — token counts are still tracked for observability
    "mock":              {"input":  0.00, "output":  0.00},
}
_DEFAULT = {"input": 3.00, "output": 15.00}  # fallback for unknown model IDs


@dataclass
class _Call:
    agent: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float


class CostTracker:
    def __init__(self):
        self._calls: list[_Call] = []

    def track(self, agent_name: str, model: str, input_tokens: int, output_tokens: int) -> float:
        p = _PRICING.get(model, _DEFAULT)
        cost = (input_tokens * p["input"] + output_tokens * p["output"]) / 1_000_000
        self._calls.append(_Call(agent_name, model, input_tokens, output_tokens, cost))
        return cost

    @property
    def total_tokens(self) -> int:
        return sum(c.input_tokens + c.output_tokens for c in self._calls)

    def total_cost(self) -> float:
        return round(sum(c.cost_usd for c in self._calls), 8)

    def summary(self) -> dict:
        return {
            "total_tokens": self.total_tokens,
            "total_input_tokens":  sum(c.input_tokens  for c in self._calls),
            "total_output_tokens": sum(c.output_tokens for c in self._calls),
            "total_cost_usd": self.total_cost(),
            "per_agent": [
                {
                    "agent": c.agent, "model": c.model,
                    "input_tokens": c.input_tokens,
                    "output_tokens": c.output_tokens,
                    "cost_usd": c.cost_usd,
                }
                for c in self._calls
            ],
        }
