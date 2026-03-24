"""
Unit tests for the FORION integration layer.

Tests config loading, type normalization, routing hints, hook manager,
and the ForionCustomLogger callback.
"""

import asyncio
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from litellm.proxy.forion.config import (
    ForionConfig,
    ProductModelConfig,
    load_forion_config,
)
from litellm.proxy.forion.hooks import (
    ForionCustomLogger,
    ForionHookManager,
    _extract_forion_metadata,
    forion_hook_manager,
)
from litellm.proxy.forion.logging import log_forion_request
from litellm.proxy.forion.routing import get_fallback_models, resolve_model_for_product
from litellm.proxy.forion.types import (
    ForionResponseMetadata,
    ForionTokenUsage,
    normalize_product,
)


# -----------------------------------------------------------------------
# types.py
# -----------------------------------------------------------------------
class TestNormalizeProduct:
    def test_valid_products(self):
        assert normalize_product("ide") == "ide"
        assert normalize_product("spark") == "spark"
        assert normalize_product("orbit") == "orbit"

    def test_case_insensitive(self):
        assert normalize_product("IDE") == "ide"
        assert normalize_product("Spark") == "spark"

    def test_unknown_values(self):
        assert normalize_product("invalid") == "unknown"
        assert normalize_product("") == "unknown"
        assert normalize_product(None) == "unknown"


class TestForionResponseMetadata:
    def test_create_response_metadata(self):
        meta = ForionResponseMetadata(
            product="spark",
            estimated_cost="0.001234",
            tokens_used=ForionTokenUsage(input=100, output=50),
        )
        assert meta["product"] == "spark"
        assert meta["estimated_cost"] == "0.001234"
        assert meta["tokens_used"]["input"] == 100
        assert meta["tokens_used"]["output"] == 50


# -----------------------------------------------------------------------
# config.py
# -----------------------------------------------------------------------
class TestLoadForionConfig:
    def test_missing_section_returns_defaults(self):
        cfg = load_forion_config({})
        assert cfg.enabled is False
        assert cfg.default_product == "ide"
        assert cfg.model_mapping == {}

    def test_none_input(self):
        cfg = load_forion_config(None)
        assert cfg.enabled is False

    def test_full_config(self):
        raw = {
            "forion": {
                "enabled": True,
                "default_product": "spark",
                "model_mapping": {
                    "ide": {"default": "gpt-4o-mini", "fallback": ["gpt-4o"]},
                    "spark": {"default": "gpt-4o", "fallback": ["claude-3-5-sonnet"]},
                },
            }
        }
        cfg = load_forion_config(raw)
        assert cfg.enabled is True
        assert cfg.default_product == "spark"
        assert "ide" in cfg.model_mapping
        assert cfg.model_mapping["ide"].default == "gpt-4o-mini"
        assert cfg.model_mapping["ide"].fallback == ["gpt-4o"]
        assert cfg.model_mapping["spark"].default == "gpt-4o"

    def test_malformed_section_does_not_crash(self):
        cfg = load_forion_config({"forion": "not_a_dict"})
        assert cfg.enabled is False

    def test_partial_model_mapping(self):
        raw = {
            "forion": {
                "enabled": True,
                "model_mapping": {
                    "orbit": {"default": "gpt-4o-mini"},
                },
            }
        }
        cfg = load_forion_config(raw)
        assert cfg.model_mapping["orbit"].default == "gpt-4o-mini"
        assert cfg.model_mapping["orbit"].fallback == []


class TestForionConfigGetProductConfig:
    def test_existing_product(self):
        cfg = ForionConfig(
            enabled=True,
            model_mapping={"ide": ProductModelConfig(default="gpt-4o-mini")},
        )
        assert cfg.get_product_config("ide") is not None
        assert cfg.get_product_config("ide").default == "gpt-4o-mini"

    def test_missing_product(self):
        cfg = ForionConfig(enabled=True)
        assert cfg.get_product_config("spark") is None


# -----------------------------------------------------------------------
# routing.py
# -----------------------------------------------------------------------
class TestResolveModelForProduct:
    def _enabled_config(self) -> ForionConfig:
        return ForionConfig(
            enabled=True,
            model_mapping={
                "ide": ProductModelConfig(default="gpt-4o-mini", fallback=["gpt-4o"]),
                "spark": ProductModelConfig(default="gpt-4o"),
            },
        )

    def test_disabled_config_passthrough(self):
        cfg = ForionConfig(enabled=False)
        assert resolve_model_for_product("ide", cfg, "my-model") == "my-model"

    def test_unknown_product_passthrough(self):
        cfg = self._enabled_config()
        assert resolve_model_for_product("unknown", cfg, "my-model") == "my-model"

    def test_no_product_passthrough(self):
        cfg = self._enabled_config()
        assert resolve_model_for_product(None, cfg, "my-model") == "my-model"

    def test_product_with_existing_model_is_preserved(self):
        cfg = self._enabled_config()
        # Caller already specified a model — don't override
        assert resolve_model_for_product("ide", cfg, "my-model") == "my-model"

    def test_product_fills_missing_model(self):
        cfg = self._enabled_config()
        assert resolve_model_for_product("ide", cfg, None) == "gpt-4o-mini"
        assert resolve_model_for_product("ide", cfg, "") == "gpt-4o-mini"

    def test_unmapped_product_passthrough(self):
        cfg = self._enabled_config()
        assert resolve_model_for_product("orbit", cfg, None) is None


class TestGetFallbackModels:
    def test_returns_fallback_list(self):
        cfg = ForionConfig(
            enabled=True,
            model_mapping={
                "ide": ProductModelConfig(default="x", fallback=["a", "b"]),
            },
        )
        assert get_fallback_models("ide", cfg) == ["a", "b"]

    def test_disabled_returns_empty(self):
        cfg = ForionConfig(enabled=False)
        assert get_fallback_models("ide", cfg) == []

    def test_unmapped_product_returns_empty(self):
        cfg = ForionConfig(
            enabled=True,
            model_mapping={"ide": ProductModelConfig(default="x")},
        )
        assert get_fallback_models("spark", cfg) == []


# -----------------------------------------------------------------------
# hooks.py — ForionHookManager
# -----------------------------------------------------------------------
class TestForionHookManager:
    @pytest.mark.asyncio
    async def test_before_request_hooks_run_in_order(self):
        mgr = ForionHookManager()
        calls = []

        async def hook_a(data):
            calls.append("a")
            data["a"] = True
            return data

        async def hook_b(data):
            calls.append("b")
            data["b"] = True
            return data

        mgr.register_before_request(hook_a)
        mgr.register_before_request(hook_b)

        result = await mgr.run_before_request({"initial": True})
        assert calls == ["a", "b"]
        assert result["a"] is True
        assert result["b"] is True
        assert result["initial"] is True

    @pytest.mark.asyncio
    async def test_before_request_hook_error_is_swallowed(self):
        mgr = ForionHookManager()

        async def bad_hook(data):
            raise ValueError("boom")

        async def good_hook(data):
            data["ok"] = True
            return data

        mgr.register_before_request(bad_hook)
        mgr.register_before_request(good_hook)

        result = await mgr.run_before_request({})
        assert result["ok"] is True  # bad_hook didn't crash the chain

    @pytest.mark.asyncio
    async def test_after_response_hooks_run(self):
        mgr = ForionHookManager()
        captured = {}

        async def hook(data):
            captured.update(data)

        mgr.register_after_response(hook)
        await mgr.run_after_response({"product": "spark"})
        assert captured["product"] == "spark"

    @pytest.mark.asyncio
    async def test_after_response_hook_error_is_swallowed(self):
        mgr = ForionHookManager()

        async def bad_hook(data):
            raise RuntimeError("fail")

        mgr.register_after_response(bad_hook)
        # Should not raise
        await mgr.run_after_response({"x": 1})


# -----------------------------------------------------------------------
# hooks.py — _extract_forion_metadata
# -----------------------------------------------------------------------
class TestExtractForionMetadata:
    def test_full_metadata(self):
        meta = _extract_forion_metadata(
            {"product": "spark", "user_id": "u1", "workspace_id": "w1"}
        )
        assert meta["product"] == "spark"
        assert meta["user_id"] == "u1"
        assert meta["workspace_id"] == "w1"

    def test_missing_fields_default(self):
        meta = _extract_forion_metadata({})
        assert meta["product"] == "unknown"
        assert meta["user_id"] is None
        assert meta["workspace_id"] is None

    def test_none_input(self):
        meta = _extract_forion_metadata(None)
        assert meta["product"] == "unknown"


# -----------------------------------------------------------------------
# hooks.py — ForionCustomLogger
# -----------------------------------------------------------------------
class TestForionCustomLogger:
    @pytest.mark.asyncio
    async def test_pre_call_noop_when_disabled(self):
        logger = ForionCustomLogger()
        logger._forion_config = ForionConfig(enabled=False)
        # Should not raise
        await logger.async_log_pre_api_call("gpt-4o", [], {})

    @pytest.mark.asyncio
    async def test_pre_call_extracts_metadata(self):
        logger = ForionCustomLogger()
        logger._forion_config = ForionConfig(enabled=True)

        metadata = {"product": "orbit", "user_id": "u42"}
        kwargs = {"litellm_params": {"metadata": metadata}}

        await logger.async_log_pre_api_call("gpt-4o", [], kwargs)

        assert metadata["forion_product"] == "orbit"
        assert metadata["forion_user_id"] == "u42"

    @pytest.mark.asyncio
    async def test_success_event_injects_hidden_params(self):
        logger = ForionCustomLogger()
        logger._forion_config = ForionConfig(enabled=True)

        metadata = {"forion_product": "ide", "forion_user_id": "u1"}

        # Simulate a response object with _hidden_params
        response = MagicMock()
        response._hidden_params = {}

        kwargs = {
            "litellm_params": {"metadata": metadata},
            "model": "gpt-4o",
            "standard_logging_object": {
                "prompt_tokens": 50,
                "completion_tokens": 25,
                "response_cost": 0.0015,
            },
        }

        await logger.async_log_success_event(kwargs, response, None, None)

        assert "forion_metadata" in response._hidden_params
        fm = response._hidden_params["forion_metadata"]
        assert fm["product"] == "ide"
        assert fm["tokens_used"]["input"] == 50
        assert fm["tokens_used"]["output"] == 25
        assert fm["estimated_cost"] == "0.001500"

    @pytest.mark.asyncio
    async def test_success_event_noop_when_disabled(self):
        logger = ForionCustomLogger()
        logger._forion_config = ForionConfig(enabled=False)

        response = MagicMock()
        response._hidden_params = {}

        await logger.async_log_success_event(
            {"litellm_params": {"metadata": {}}}, response, None, None
        )
        # hidden_params should NOT have forion_metadata
        assert "forion_metadata" not in response._hidden_params


# -----------------------------------------------------------------------
# logging.py
# -----------------------------------------------------------------------
class TestLogForionRequest:
    def test_does_not_raise(self):
        """Smoke test: should never raise regardless of inputs."""
        log_forion_request()
        log_forion_request(
            product="ide",
            user_id="u1",
            model="gpt-4o",
            tokens_in=100,
            tokens_out=50,
            cost=0.002,
            workspace_id="ws1",
        )
        log_forion_request(product="unknown", cost=None, tokens_in=None)
