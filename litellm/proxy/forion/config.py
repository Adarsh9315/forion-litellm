"""
FORION configuration.

Reads the optional ``forion:`` section from the proxy config YAML.
If the section is missing or malformed the integration is silently disabled —
no crash, no side-effects.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ProductModelConfig:
    """Model routing config for a single FORION product."""

    default: str = ""
    fallback: List[str] = field(default_factory=list)


@dataclass
class ForionConfig:
    """Top-level FORION configuration."""

    enabled: bool = False
    default_product: str = "ide"
    model_mapping: Dict[str, ProductModelConfig] = field(default_factory=dict)

    def get_product_config(self, product: str) -> Optional[ProductModelConfig]:
        """Return model config for *product*, or None if not mapped."""
        return self.model_mapping.get(product)


def load_forion_config(yaml_dict: Optional[Dict[str, Any]] = None) -> ForionConfig:
    """
    Build a ``ForionConfig`` from a raw config dict (typically the full
    proxy config YAML).  Returns a disabled default when the section is
    absent or unparseable.
    """
    if not yaml_dict or not isinstance(yaml_dict, dict):
        return ForionConfig()

    raw: Any = yaml_dict.get("forion")
    if not raw or not isinstance(raw, dict):
        return ForionConfig()

    try:
        enabled = bool(raw.get("enabled", False))
        default_product = str(raw.get("default_product", "ide"))
        model_mapping: Dict[str, ProductModelConfig] = {}

        raw_mapping = raw.get("model_mapping")
        if isinstance(raw_mapping, dict):
            for product_key, product_val in raw_mapping.items():
                if isinstance(product_val, dict):
                    model_mapping[str(product_key)] = ProductModelConfig(
                        default=str(product_val.get("default", "")),
                        fallback=list(product_val.get("fallback", [])),
                    )

        return ForionConfig(
            enabled=enabled,
            default_product=default_product,
            model_mapping=model_mapping,
        )
    except Exception:
        # Never crash the proxy because of a bad forion config
        return ForionConfig()
