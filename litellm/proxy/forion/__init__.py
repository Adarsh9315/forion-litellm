"""
FORION integration for LiteLLM proxy.

A self-contained, non-breaking extension that makes the proxy aware of
FORION product context (ide / spark / orbit) without modifying any core
LiteLLM code.

Quick-start — add to your proxy config YAML::

    forion:
      enabled: true
      default_product: "ide"
      model_mapping:
        ide:
          default: "gpt-4o-mini"
          fallback: ["gpt-4o"]
        spark:
          default: "gpt-4o"
          fallback: ["claude-3-5-sonnet"]
        orbit:
          default: "gpt-4o-mini"
          fallback: ["gpt-4o-mini"]

    litellm_settings:
      callbacks: ["litellm.proxy.forion.hooks.ForionCustomLogger"]
"""

from litellm.proxy.forion.config import ForionConfig, load_forion_config
from litellm.proxy.forion.hooks import (
    ForionCustomLogger,
    ForionHookManager,
    forion_hook_manager,
)

__all__ = [
    "ForionConfig",
    "ForionCustomLogger",
    "ForionHookManager",
    "forion_hook_manager",
    "load_forion_config",
]
