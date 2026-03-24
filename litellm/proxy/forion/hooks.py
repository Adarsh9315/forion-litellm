"""
FORION middleware hooks and CustomLogger integration.

``ForionCustomLogger`` plugs into LiteLLM's callback system to:
  1. Extract FORION metadata (product / user_id / workspace_id) from
     request metadata — these pass through safely if present.
  2. Emit enhanced structured logs with product context.
  3. Inject ``forion_metadata`` into response hidden_params so downstream
     consumers (e.g. a NestJS gateway) can read it from headers.
  4. Invoke optional ``before_request`` / ``after_response`` hooks for
     external system integration.

All behaviour is guarded by ``ForionConfig.enabled``.  When disabled (or
when the ``forion:`` config section is missing), this logger is a no-op.
"""

import traceback
from typing import Any, Awaitable, Callable, Dict, List, Optional, Union

from litellm._logging import verbose_proxy_logger
from litellm.integrations.custom_logger import CustomLogger
from litellm.proxy.forion.config import ForionConfig, load_forion_config
from litellm.proxy.forion.logging import log_forion_request
from litellm.proxy.forion.routing import resolve_model_for_product
from litellm.proxy.forion.types import (
    ForionResponseMetadata,
    ForionTokenUsage,
    normalize_product,
)

# ---------------------------------------------------------------------------
# Hook types — external systems register async callables here
# ---------------------------------------------------------------------------
BeforeRequestHook = Callable[[Dict[str, Any]], Awaitable[Optional[Dict[str, Any]]]]
AfterResponseHook = Callable[[Dict[str, Any]], Awaitable[None]]


class ForionHookManager:
    """
    Registry for optional ``before_request`` / ``after_response`` hooks.

    Hooks are async callables.  Multiple hooks of the same type can be
    registered and they run sequentially.  A failing hook is logged but
    never interrupts the main request flow.
    """

    def __init__(self) -> None:
        self._before_request_hooks: List[BeforeRequestHook] = []
        self._after_response_hooks: List[AfterResponseHook] = []

    def register_before_request(self, hook: BeforeRequestHook) -> None:
        self._before_request_hooks.append(hook)

    def register_after_response(self, hook: AfterResponseHook) -> None:
        self._after_response_hooks.append(hook)

    async def run_before_request(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """Run all before_request hooks.  Returns (possibly mutated) request_data."""
        data = request_data
        for hook in self._before_request_hooks:
            try:
                result = await hook(data)
                if isinstance(result, dict):
                    data = result
            except Exception:
                verbose_proxy_logger.warning(
                    "forion before_request hook error: %s", traceback.format_exc()
                )
        return data

    async def run_after_response(self, response_data: Dict[str, Any]) -> None:
        """Run all after_response hooks (fire-and-forget style)."""
        for hook in self._after_response_hooks:
            try:
                await hook(response_data)
            except Exception:
                verbose_proxy_logger.warning(
                    "forion after_response hook error: %s", traceback.format_exc()
                )


# Singleton hook manager — importable by external code that wants to
# register hooks (e.g. a NestJS bridge service).
forion_hook_manager = ForionHookManager()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_forion_metadata(metadata: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Pull FORION-specific fields from request metadata, defaulting safely."""
    if not metadata or not isinstance(metadata, dict):
        return {"product": "unknown", "user_id": None, "workspace_id": None}
    return {
        "product": normalize_product(metadata.get("product")),
        "user_id": metadata.get("user_id"),
        "workspace_id": metadata.get("workspace_id"),
    }


# ---------------------------------------------------------------------------
# CustomLogger subclass
# ---------------------------------------------------------------------------

class ForionCustomLogger(CustomLogger):
    """
    LiteLLM custom callback that makes the proxy FORION-aware.

    Register in config YAML:
        litellm_settings:
          callbacks: ["litellm.proxy.forion.hooks.ForionCustomLogger"]
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._forion_config: Optional[ForionConfig] = None

    # ------------------------------------------------------------------
    # Config bootstrap — lazily loaded from proxy_config on first call
    # ------------------------------------------------------------------

    def _ensure_config(self) -> ForionConfig:
        if self._forion_config is not None:
            return self._forion_config
        try:
            from litellm.proxy.proxy_server import proxy_config

            raw_config: Dict[str, Any] = getattr(proxy_config, "config", {}) or {}
            self._forion_config = load_forion_config(raw_config)
        except Exception:
            self._forion_config = ForionConfig()
        return self._forion_config

    # ------------------------------------------------------------------
    # Pre-call: extract metadata, apply routing hints, run hooks
    # ------------------------------------------------------------------

    async def async_log_pre_api_call(
        self, model: str, messages: Any, kwargs: Dict[str, Any]
    ) -> None:
        cfg = self._ensure_config()
        if not cfg.enabled:
            return

        litellm_params = kwargs.get("litellm_params") or {}
        metadata: Dict[str, Any] = litellm_params.get("metadata") or {}

        forion_meta = _extract_forion_metadata(metadata)
        product = forion_meta["product"]

        # Persist the normalised product back into metadata so downstream
        # callbacks can consume it without re-parsing.
        metadata["forion_product"] = product
        metadata["forion_user_id"] = forion_meta.get("user_id")
        metadata["forion_workspace_id"] = forion_meta.get("workspace_id")

        # Routing hint — only provides a default when no model was given
        resolved = resolve_model_for_product(product, cfg, model)
        if resolved and resolved != model:
            verbose_proxy_logger.debug(
                "forion routing: product=%s resolved model %s -> %s",
                product,
                model,
                resolved,
            )

        # Run registered before_request hooks
        hook_data = {
            "model": model,
            "messages": messages,
            "metadata": metadata,
            "forion": forion_meta,
        }
        await forion_hook_manager.run_before_request(hook_data)

    # ------------------------------------------------------------------
    # Post-call: build response metadata, enhanced logging, hooks
    # ------------------------------------------------------------------

    async def async_log_success_event(
        self,
        kwargs: Dict[str, Any],
        response_obj: Any,
        start_time: Any,
        end_time: Any,
    ) -> None:
        cfg = self._ensure_config()
        if not cfg.enabled:
            return

        litellm_params = kwargs.get("litellm_params") or {}
        metadata: Dict[str, Any] = litellm_params.get("metadata") or {}

        product = str(metadata.get("forion_product", "unknown"))
        user_id = metadata.get("forion_user_id")
        workspace_id = metadata.get("forion_workspace_id")

        # Extract token/cost info from standard logging object if available
        sl_object: Optional[Dict[str, Any]] = kwargs.get("standard_logging_object")
        tokens_in: Optional[int] = None
        tokens_out: Optional[int] = None
        cost: Optional[float] = None
        model: Optional[str] = kwargs.get("model")

        if sl_object and isinstance(sl_object, dict):
            tokens_in = sl_object.get("prompt_tokens")
            tokens_out = sl_object.get("completion_tokens")
            cost = sl_object.get("response_cost")

        # --- Enhanced logging ---
        log_forion_request(
            product=product,
            user_id=user_id,
            model=model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost=cost,
            workspace_id=workspace_id,
        )

        # --- Build forion_metadata for the response ---
        forion_resp = ForionResponseMetadata(
            product=product,
            estimated_cost=f"{cost:.6f}" if cost is not None else None,
            tokens_used=ForionTokenUsage(
                input=tokens_in or 0,
                output=tokens_out or 0,
            ),
        )

        # Inject into hidden_params (LiteLLM's standard extension point for
        # response enrichment — consumed by get_custom_headers).
        if hasattr(response_obj, "_hidden_params"):
            hidden = getattr(response_obj, "_hidden_params", None)
            if isinstance(hidden, dict):
                hidden["forion_metadata"] = dict(forion_resp)

        # --- Run after_response hooks ---
        hook_data = {
            "response": response_obj,
            "forion_metadata": dict(forion_resp),
            "kwargs": kwargs,
        }
        await forion_hook_manager.run_after_response(hook_data)
