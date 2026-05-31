"""
Minimal StateGraph that mirrors langgraph.graph.StateGraph 0.2.x API.
Used automatically when `langgraph` is not installed.

Merging rules (applied in order per returned key):
  - list  → appended   (matches langgraph Annotated[list, operator.add])
  - dict  → shallow-merged
  - other → replaced
"""

_END_SENTINEL = "__END__"
END = _END_SENTINEL


class _CompiledGraph:
    def __init__(self, nodes, entry, plain_edges, conditional_edges):
        self._nodes = nodes
        self._entry = entry
        self._plain = plain_edges        # {src: dst}
        self._conditional = conditional_edges  # {src: (fn, {label: dst})}

    def invoke(self, state: dict) -> dict:
        current = self._entry
        seen: set[str] = set()

        while current and current != _END_SENTINEL:
            if current in seen:
                break  # cycle guard
            seen.add(current)

            fn = self._nodes.get(current)
            if fn is None:
                break

            updates = fn(state) or {}

            # Merge updates → new state
            merged = dict(state)
            for key, val in updates.items():
                existing = merged.get(key)
                if isinstance(val, list) and isinstance(existing, list):
                    merged[key] = existing + val
                elif isinstance(val, dict) and isinstance(existing, dict):
                    merged[key] = {**existing, **val}
                else:
                    merged[key] = val
            state = merged

            # Routing
            if current in self._conditional:
                route_fn, mapping = self._conditional[current]
                label = route_fn(state)
                current = mapping.get(label, _END_SENTINEL)
            elif current in self._plain:
                current = self._plain[current]
            else:
                break

        return state


class StateGraph:
    """Drop-in fallback for ``langgraph.graph.StateGraph``."""

    def __init__(self, schema=None):
        self._nodes: dict = {}
        self._plain: dict = {}
        self._conditional: dict = {}
        self._entry: str | None = None

    def add_node(self, name: str, fn):
        self._nodes[name] = fn

    def set_entry_point(self, name: str):
        self._entry = name

    def add_edge(self, src: str, dst):
        self._plain[src] = dst

    def add_conditional_edges(self, src: str, fn, mapping: dict):
        self._conditional[src] = (fn, dict(mapping))

    def compile(self) -> _CompiledGraph:
        return _CompiledGraph(self._nodes, self._entry, self._plain, self._conditional)
