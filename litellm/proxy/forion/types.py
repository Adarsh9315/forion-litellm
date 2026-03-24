"""
FORION type definitions.

Defines product identifiers and metadata structures used across the FORION
integration layer. All types are optional extensions — they do not modify
any existing LiteLLM types.
"""

from typing import Any, Dict, List, Literal, Optional

from typing_extensions import TypedDict

# Valid FORION product identifiers
ForionProduct = Literal["ide", "spark", "orbit", "unknown"]

VALID_FORION_PRODUCTS: List[str] = ["ide", "spark", "orbit"]


def normalize_product(value: Optional[str]) -> ForionProduct:
    """Safely coerce an arbitrary string to a ForionProduct."""
    if value and value.lower() in VALID_FORION_PRODUCTS:
        return value.lower()  # type: ignore[return-value]
    return "unknown"


class ForionRequestMetadata(TypedDict, total=False):
    """Optional metadata fields callers may include in request ``metadata``."""

    product: str  # "ide" | "spark" | "orbit"
    user_id: str
    workspace_id: str


class ForionTokenUsage(TypedDict, total=False):
    input: int
    output: int


class ForionResponseMetadata(TypedDict, total=False):
    """Metadata appended to responses (via headers / hidden_params)."""

    product: str
    estimated_cost: Optional[str]
    tokens_used: ForionTokenUsage
