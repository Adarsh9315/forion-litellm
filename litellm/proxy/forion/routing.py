"""
FORION lightweight routing hints.

Resolves a preferred model based on the FORION product identifier.
Only takes effect when a product is provided **and** the config has a
mapping for that product.  Otherwise the original model is returned
unchanged, preserving default LiteLLM behaviour.
"""

from typing import List, Optional

from litellm.proxy.forion.config import ForionConfig


def resolve_model_for_product(
    product: Optional[str],
    forion_config: ForionConfig,
    original_model: Optional[str] = None,
) -> Optional[str]:
    """
    Return the preferred model for *product* if one is configured,
    otherwise return *original_model* unmodified.

    This is intentionally non-invasive: if the caller already specified
    a model, we only override it when there is an explicit product
    mapping *and* the original model is absent or empty.
    """
    if not forion_config.enabled or not product or product == "unknown":
        return original_model

    product_cfg = forion_config.get_product_config(product)
    if product_cfg is None:
        return original_model

    # Only provide a default when the caller did not request a specific model
    if original_model:
        return original_model

    return product_cfg.default or original_model


def get_fallback_models(
    product: Optional[str],
    forion_config: ForionConfig,
) -> List[str]:
    """
    Return fallback model list for *product*, or an empty list.
    """
    if not forion_config.enabled or not product or product == "unknown":
        return []

    product_cfg = forion_config.get_product_config(product)
    if product_cfg is None:
        return []

    return list(product_cfg.fallback)
