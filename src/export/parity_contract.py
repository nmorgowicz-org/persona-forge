"""Dependency-free validation helpers shared by model parity tools and Tier 1 tests."""


def require_output_head(output_heads, head_index: int):
    """Return a required output head or fail instead of silently reducing parity scope."""
    if not output_heads:
        raise RuntimeError("required output heads are unavailable; token parity cannot be skipped")
    if head_index >= len(output_heads):
        raise RuntimeError(
            f"missing output head {head_index}; only {len(output_heads)} heads are available"
        )
    return output_heads[head_index]
