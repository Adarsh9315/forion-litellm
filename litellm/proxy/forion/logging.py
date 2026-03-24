"""
FORION enhanced logging.

Appends structured FORION fields (product, user_id, model, tokens, cost)
to existing proxy log lines.  Uses the standard ``litellm._logging``
verbose_proxy_logger so output follows whatever log handler the operator
has configured.
"""

import logging
from typing import Optional

from litellm._logging import verbose_proxy_logger


def log_forion_request(
    product: str = "unknown",
    user_id: Optional[str] = None,
    model: Optional[str] = None,
    tokens_in: Optional[int] = None,
    tokens_out: Optional[int] = None,
    cost: Optional[float] = None,
    workspace_id: Optional[str] = None,
    level: int = logging.INFO,
) -> None:
    """
    Emit a structured log line with FORION context fields.

    This is additive — it does **not** replace or suppress any existing
    LiteLLM log output.
    """
    verbose_proxy_logger.log(
        level,
        "forion_request product=%s user_id=%s workspace_id=%s model=%s "
        "tokens_in=%s tokens_out=%s cost=%s",
        product,
        user_id or "n/a",
        workspace_id or "n/a",
        model or "n/a",
        tokens_in if tokens_in is not None else "n/a",
        tokens_out if tokens_out is not None else "n/a",
        f"{cost:.6f}" if cost is not None else "n/a",
    )
