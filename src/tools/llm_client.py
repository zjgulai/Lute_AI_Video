"""Unified LLM client with exact DeepSeek paid-mutation accounting.

Configured paid calls are admitted only after a tenant/job execution context has
reserved the frozen maximum request envelope.  The provider mutation runs once,
and exact response usage is durably settled before content is returned.

Preferred usage from async code:    await llm.invoke(...)
                                   await llm.invoke_json(...)

SSOT for per-request API keys: _request_api_keys ContextVar.
Callers (e.g. api.py) set this per-request so that concurrent pipelines do not
contaminate each other's keys via the global os.environ.
"""

from __future__ import annotations

import asyncio
import contextvars
import hashlib
import json
import os
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import ValidationError

from src.config import (
    DEEPSEEK_API_BASE,
    DEEPSEEK_MODEL,
    DEFAULT_LLM_PROVIDER,
)
from src.models.provider_cost import (
    LLMTokensBillingFacts,
    ProviderCostContractError,
)
from src.services.provider_cost import (
    ProviderCostOperationDefinition,
    ProviderCostService,
    build_provider_cost_service,
)
from src.services.provider_execution import (
    ProviderExecutionContext,
    get_provider_execution_context,
)
from src.services.provider_price_catalog import (
    DeepSeekModelContract,
    ProviderPriceCatalog,
)

# Optional SDK import — only needed when a paid mutation is admitted.
try:
    from langchain_openai import ChatOpenAI
except ImportError:
    ChatOpenAI = None

logger = structlog.get_logger()

# Timeout per LLM call in seconds — prevents pipeline hangs on dead connections.
# 60s lets DeepSeek finish typical structured outputs while bounding the period
# before an uncertain acknowledgement is durably held as ambiguous.
LLM_TIMEOUT_SECONDS = 60.0

# Client cache TTL — LangChain client objects hold HTTP connections; refreshing
# periodically prevents stale connection pools without rebuilding per request.
CLIENT_CACHE_TTL_SECONDS = 300  # 5 minutes

# Max cached clients per LLMClient instance — prevents unbounded memory growth
# when many unique (provider, model, key_hash) combinations are used.
CLIENT_CACHE_MAX_SIZE = 20

DEEPSEEK_GLOBAL_ENDPOINT = "https://api.deepseek.com"
DEFAULT_LLM_OPERATION_KEY = "llm.chat.default"
LLM_RESERVATION_TTL_SECONDS = 300

# Finite, code-owned provider operation vocabulary. Callers select one stable
# workflow template and, for multi-item work, a bounded server-owned instance
# slot. Prompt digests stay in the immutable fingerprint only.
DEEPSEEK_LLM_OPERATION_MODELS = MappingProxyType(
    {
        DEFAULT_LLM_OPERATION_KEY: "deepseek-v4-pro",
        "fast.prompt_enhance": "deepseek-v4-flash",
        "agent.strategy": "deepseek-v4-flash",
        "agent.script_writer": "deepseek-v4-flash",
        "skill.product_strategy": "deepseek-v4-flash",
        "skill.script_writer": "deepseek-v4-flash",
        "skill.video_analysis": "deepseek-v4-pro",
        "tool.translate": "deepseek-v4-pro",
        "skill.remix_script": "deepseek-v4-pro",
        "skill.llm": "deepseek-v4-pro",
        "pipeline.s5.vlog_strategy": "deepseek-v4-pro",
        "pipeline.candidate_scorer": "deepseek-v4-pro",
        "agent.compliance": "deepseek-v4-pro",
        "agent.storyboard": "deepseek-v4-pro",
        "admin.provider_connectivity": "deepseek-v4-pro",
    }
)

_SAFE_OPERATION_INSTANCE_RE = re.compile(r"^[a-z][a-z0-9_.:-]{0,63}$")

ProviderCostServiceFactory = Callable[
    [Mapping[str, ProviderCostOperationDefinition]],
    ProviderCostService,
]

# Per-request API keys — prevents cross-request contamination via os.environ.
# Set by api.py _inject_api_keys before pipeline execution.
_request_api_keys: contextvars.ContextVar[dict[str, str]] = contextvars.ContextVar("request_api_keys", default={})


def set_request_api_keys(keys: dict[str, str]) -> None:
    """Set API keys for the current request context."""
    _request_api_keys.set(keys)


def get_request_api_key(env_name: str) -> str | None:
    """Get an API key from request context, falling back to os.environ."""
    request_keys = _request_api_keys.get()
    if env_name in request_keys:
        return request_keys[env_name]
    return os.environ.get(env_name)


class LLMTimeoutError(asyncio.TimeoutError):
    """Deprecated compatibility symbol; paid timeouts now surface ambiguity."""


class LLMNotConfiguredError(RuntimeError):
    """Explicit no-key branch that creates no provider-cost attempt."""


@dataclass(frozen=True, slots=True)
class _LLMSubmissionPermit:
    """Private proof that reserve and submission_started succeeded."""

    provider: str
    canonical_model: str
    endpoint: str
    max_completion_tokens: int
    attempt_id: str


@dataclass(frozen=True, slots=True)
class _PreparedLLMMutation:
    context: ProviderExecutionContext
    canonical_model: str
    operation_key: str
    operation_instance: str
    logical_operation: str
    attempt_fingerprint: str
    definition: ProviderCostOperationDefinition
    model_contract: DeepSeekModelContract


class LLMClient:
    """DeepSeek client with exact accounting and structured-output parsing.

    A missing key is the only zero-attempt local fallback signal. Configured
    calls require a bound execution context, mutate once, and never return paid
    content before durable usage settlement.
    """

    def __init__(
        self,
        provider: str | None = None,
        timeout: float = LLM_TIMEOUT_SECONDS,
        *,
        price_catalog: ProviderPriceCatalog | None = None,
        cost_service_factory: ProviderCostServiceFactory | None = None,
    ):
        self.provider = provider or DEFAULT_LLM_PROVIDER
        self.timeout = timeout
        self._clients: dict[str, Any] = {}
        # TTL tracking: cache_key → created_at timestamp
        self._clients_ts: dict[str, float] = {}
        self._price_catalog = price_catalog or ProviderPriceCatalog.load_default()
        if not isinstance(self._price_catalog, ProviderPriceCatalog):
            raise ProviderCostContractError(
                "provider_cost_rule_unavailable",
                "provider price catalog injection is invalid",
            )
        if cost_service_factory is not None and not callable(cost_service_factory):
            raise ProviderCostContractError(
                "provider_cost_store_unavailable",
                "provider cost service factory is invalid",
            )
        self._cost_service_factory = cost_service_factory or self._build_cost_service

    def _build_cost_service(
        self,
        registry: Mapping[str, ProviderCostOperationDefinition],
    ) -> ProviderCostService:
        return build_provider_cost_service(
            operation_registry=registry,
            price_catalog=self._price_catalog,
        )

    def _resolve_api_key(self, env_name: str) -> str | None:
        """Resolve API key from request context or global env."""
        return get_request_api_key(env_name)

    def is_configured(self) -> bool:
        """Return True if an API key is available for the configured provider.

        Checks the request-scoped key first (contextvars), then falls back
        to the global environment variable.
        """
        if self.provider == "anthropic":
            value = self._resolve_api_key("ANTHROPIC_API_KEY")
        elif self.provider == "kimi":
            value = self._resolve_api_key("OPENAI_API_KEY")
        elif self.provider == "deepseek":
            value = self._resolve_api_key("DEEPSEEK_API_KEY")
        else:
            value = self._resolve_api_key("OPENAI_API_KEY")
        return isinstance(value, str) and bool(value.strip())

    def _get_client(
        self,
        model: str | None = None,
        *,
        submission_permit: _LLMSubmissionPermit | None = None,
    ) -> Any:
        """Construct/reuse one SDK client only after durable submission start."""

        if not isinstance(submission_permit, _LLMSubmissionPermit):
            raise ProviderCostContractError(
                "provider_execution_context_missing",
                "LLM client construction requires a durable submission permit",
            )
        canonical_model = model or DEEPSEEK_MODEL
        if (
            self.provider != "deepseek"
            or submission_permit.provider != self.provider
            or submission_permit.canonical_model != canonical_model
            or submission_permit.endpoint != DEEPSEEK_API_BASE
            or submission_permit.max_completion_tokens != 4_096
        ):
            raise ProviderCostContractError(
                "provider_cost_attempt_conflict",
                "LLM submission permit conflicts with client construction",
            )

        key = self._resolve_api_key("DEEPSEEK_API_KEY") or ""
        if not isinstance(key, str) or not key.strip():
            raise ProviderCostContractError(
                "provider_cost_legacy_path_blocked",
                "DeepSeek credential disappeared before client construction",
            )

        # The hash is only an in-process cache dimension.  No key material is
        # logged or persisted in the provider-cost ledger.
        key_hash = hashlib.sha256(key.encode()).hexdigest()[:16]
        cache_key = f"{self.provider}:{canonical_model}:{key_hash}"
        now = time.time()

        # TTL eviction: stale clients may hold dead HTTP connections
        if cache_key in self._clients:
            ts = self._clients_ts.get(cache_key, 0)
            if now - ts > CLIENT_CACHE_TTL_SECONDS:
                del self._clients[cache_key]
                del self._clients_ts[cache_key]

        if cache_key not in self._clients:
            # Size guard: evict oldest entries when cache is full
            if len(self._clients) >= CLIENT_CACHE_MAX_SIZE:
                oldest_key = min(self._clients_ts, key=lambda k: self._clients_ts[k])
                del self._clients[oldest_key]
                del self._clients_ts[oldest_key]

            if ChatOpenAI is None:
                raise ImportError("langchain-openai is not installed")
            self._clients[cache_key] = ChatOpenAI(
                model=canonical_model,
                api_key=key,  # type: ignore[reportArgumentType]
                base_url=DEEPSEEK_API_BASE,
                temperature=0.7,
                max_completion_tokens=submission_permit.max_completion_tokens,
                timeout=self.timeout,
                max_retries=0,
            )
            self._clients_ts[cache_key] = now
        return self._clients[cache_key]

    def _prepare_paid_mutation(
        self,
        *,
        system_prompt: object,
        user_message: object,
        model: object,
        operation_key: object,
        operation_instance: object,
        max_completion_tokens: object,
    ) -> _PreparedLLMMutation:
        if not isinstance(system_prompt, str) or not isinstance(user_message, str):
            raise ProviderCostContractError(
                "provider_cost_usage_invalid",
                "LLM prompts must be text",
            )
        if self.provider != "deepseek":
            raise ProviderCostContractError(
                "provider_cost_rule_unavailable",
                "paid LLM provider is not in the exact catalog",
            )
        if not isinstance(operation_key, str):
            raise ProviderCostContractError(
                "provider_cost_rule_unavailable",
                "paid LLM operation key is invalid",
            )
        canonical_model = model if model is not None else DEEPSEEK_MODEL
        if not isinstance(canonical_model, str):
            raise ProviderCostContractError(
                "provider_cost_rule_unavailable",
                "paid LLM model is invalid",
            )
        expected_model = DEEPSEEK_LLM_OPERATION_MODELS.get(operation_key) if isinstance(operation_key, str) else None
        if expected_model is None or canonical_model != expected_model:
            raise ProviderCostContractError(
                "provider_cost_rule_unavailable",
                "paid LLM operation or canonical model is unavailable",
            )
        if DEEPSEEK_API_BASE != DEEPSEEK_GLOBAL_ENDPOINT:
            raise ProviderCostContractError(
                "provider_cost_rule_unavailable",
                "DeepSeek billing endpoint is not exact",
            )
        if max_completion_tokens is not None:
            raise ProviderCostContractError(
                "provider_cost_rule_unavailable",
                "caller completion-cap override is forbidden",
            )
        if not isinstance(operation_instance, str) or _SAFE_OPERATION_INSTANCE_RE.fullmatch(operation_instance) is None:
            raise ProviderCostContractError(
                "provider_cost_rule_unavailable",
                "paid LLM operation instance is invalid",
            )
        logical_operation = f"{operation_key}.{operation_instance}"
        if len(logical_operation) > 160:
            raise ProviderCostContractError(
                "provider_cost_rule_unavailable",
                "paid LLM logical operation is too long",
            )

        model_contract = self._price_catalog.require_model_contract(
            "deepseek",
            canonical_model,
        )
        self._price_catalog.require_rule(
            provider="deepseek",
            canonical_model=canonical_model,
            provider_billing_region="deepseek_global_usd",
            catalog_operation="chat_completion",
            media_type="text",
            billing_fact_kind="llm_tokens.v1",
            dimensions={},
        )
        if not self.is_configured():
            raise LLMNotConfiguredError("DeepSeek credential is not configured")

        context = get_provider_execution_context()
        if not isinstance(context, ProviderExecutionContext):
            raise ProviderCostContractError(
                "provider_execution_context_missing",
                "paid LLM mutation requires a bound execution context",
            )
        if context.provider_max_retries != 0:
            raise ProviderCostContractError(
                "provider_execution_context_missing",
                "paid LLM mutation retry authority is invalid",
            )

        regeneration_epoch_ref = None
        if context.regeneration_epoch is not None:
            regeneration_epoch_ref = context.regeneration_epoch.epoch_ref

        fingerprint = self._request_fingerprint(
            operation_key=operation_key,
            logical_operation=logical_operation,
            canonical_model=canonical_model,
            system_prompt=system_prompt,
            user_message=user_message,
            regeneration_epoch_ref=regeneration_epoch_ref,
        )
        definition = ProviderCostOperationDefinition(
            registry_key=operation_key,
            logical_operation=logical_operation,
            provider="deepseek",
            canonical_model=canonical_model,
            provider_billing_region="deepseek_global_usd",
            catalog_operation="chat_completion",
            media_type="text",
            billing_fact_kind="llm_tokens.v1",
            dimensions=(),
            reservation_billing_facts=LLMTokensBillingFacts(
                schema_version="llm_tokens.v1",
                input_tokens=model_contract.input_reservation_ceiling_tokens,
                input_cache_hit_tokens=0,
                input_cache_miss_tokens=model_contract.input_reservation_ceiling_tokens,
                output_tokens=model_contract.application_max_output_tokens,
                total_tokens=(
                    model_contract.input_reservation_ceiling_tokens + model_contract.application_max_output_tokens
                ),
            ),
            reservation_ttl_seconds=LLM_RESERVATION_TTL_SECONDS,
        )
        return _PreparedLLMMutation(
            context=context,
            canonical_model=canonical_model,
            operation_key=operation_key,
            operation_instance=operation_instance,
            logical_operation=logical_operation,
            attempt_fingerprint=fingerprint,
            definition=definition,
            model_contract=model_contract,
        )

    @staticmethod
    def _request_fingerprint(
        *,
        operation_key: str,
        logical_operation: str,
        canonical_model: str,
        system_prompt: str,
        user_message: str,
        regeneration_epoch_ref: str | None,
    ) -> str:
        payload = {
            "version": "llm-mutation-intent.v2",
            "operation_key": operation_key,
            "logical_operation": logical_operation,
            "provider": "deepseek",
            "canonical_model": canonical_model,
            "regeneration_epoch_ref": regeneration_epoch_ref,
            "system_prompt_sha256": hashlib.sha256(system_prompt.encode("utf-8")).hexdigest(),
            "user_message_sha256": hashlib.sha256(user_message.encode("utf-8")).hexdigest(),
        }
        canonical = json.dumps(
            payload,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    @staticmethod
    def _extract_deepseek_usage(response: object) -> dict[str, object]:
        metadata = getattr(response, "response_metadata", None)
        usage = metadata.get("token_usage") if isinstance(metadata, Mapping) else None
        if not isinstance(usage, Mapping):
            additional = getattr(response, "additional_kwargs", None)
            usage = additional.get("usage") if isinstance(additional, Mapping) else None
        source: Mapping[str, object] = usage if isinstance(usage, Mapping) else {}
        return {
            "schema_version": "llm_tokens.v1",
            "input_tokens": source.get("prompt_tokens"),
            "input_cache_hit_tokens": source.get("prompt_cache_hit_tokens"),
            "input_cache_miss_tokens": source.get("prompt_cache_miss_tokens"),
            "output_tokens": source.get("completion_tokens"),
            "total_tokens": source.get("total_tokens"),
        }

    @staticmethod
    def _usage_exceeds_contract(
        facts: LLMTokensBillingFacts,
        contract: DeepSeekModelContract,
    ) -> bool:
        return (
            facts.input_tokens > contract.input_reservation_ceiling_tokens
            or facts.output_tokens > contract.application_max_output_tokens
            or facts.total_tokens > contract.context_window_tokens
        )

    @staticmethod
    def _raise_replay(attempt: Mapping[str, object]) -> None:
        state = attempt.get("state")
        if state == "ambiguous":
            code = "provider_cost_outcome_ambiguous"
        elif state == "accounting_error":
            code = "provider_cost_accounting_error"
        else:
            code = "provider_cost_attempt_conflict"
        raise ProviderCostContractError(
            code,  # type: ignore[arg-type]
            "durable LLM attempt cannot be resubmitted",
        )

    async def ainvoke(
        self,
        system_prompt: str,
        user_message: str,
        model: str | None = None,
        *,
        operation_key: str = DEFAULT_LLM_OPERATION_KEY,
        operation_instance: str = "primary",
        max_completion_tokens: object = None,
    ) -> str:
        """Run one exact DeepSeek mutation and settle before returning text."""

        prepared = self._prepare_paid_mutation(
            system_prompt=system_prompt,
            user_message=user_message,
            model=model,
            operation_key=operation_key,
            operation_instance=operation_instance,
            max_completion_tokens=max_completion_tokens,
        )
        registry = {prepared.operation_key: prepared.definition}
        service = self._cost_service_factory(registry)
        if not isinstance(service, ProviderCostService):
            raise ProviderCostContractError(
                "provider_cost_store_unavailable",
                "provider cost service injection is invalid",
            )
        reservation = await service.reserve_or_replay(
            tenant_id=prepared.context.tenant_id,
            account_id=prepared.context.account_id,
            operation_key=prepared.operation_key,
            attempt_fingerprint=prepared.attempt_fingerprint,
            regeneration_epoch=prepared.context.regeneration_epoch,
        )
        if reservation.outcome != "owner":
            self._raise_replay(reservation.attempt)
        attempt_id = reservation.attempt["attempt_id"]
        await service.mark_submission_started(
            tenant_id=prepared.context.tenant_id,
            attempt_id=attempt_id,
        )
        permit = _LLMSubmissionPermit(
            provider="deepseek",
            canonical_model=prepared.canonical_model,
            endpoint=DEEPSEEK_API_BASE,
            max_completion_tokens=prepared.model_contract.application_max_output_tokens,
            attempt_id=attempt_id,
        )
        try:
            client = self._get_client(
                prepared.canonical_model,
                submission_permit=permit,
            )
        except Exception as exc:
            await service.release(
                tenant_id=prepared.context.tenant_id,
                attempt_id=attempt_id,
                expected_state="submission_started",
            )
            if isinstance(exc, ProviderCostContractError):
                raise
            raise ProviderCostContractError(
                "provider_cost_legacy_path_blocked",
                "LLM provider client construction failed before submit",
            ) from None

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_message),
        ]
        try:
            response = await asyncio.wait_for(
                _async_invoke(client, messages),
                timeout=self.timeout,
            )
        except asyncio.CancelledError:
            await asyncio.shield(
                service.mark_ambiguous(
                    tenant_id=prepared.context.tenant_id,
                    attempt_id=attempt_id,
                    expected_state="submission_started",
                )
            )
            raise
        except Exception:
            await service.mark_ambiguous(
                tenant_id=prepared.context.tenant_id,
                attempt_id=attempt_id,
                expected_state="submission_started",
            )
            logger.error(
                "llm: provider outcome ambiguous",
                safe_error_code="provider_cost_outcome_ambiguous",
            )
            raise ProviderCostContractError(
                "provider_cost_outcome_ambiguous",
                "LLM provider acknowledgement is uncertain",
            ) from None

        usage_payload = self._extract_deepseek_usage(response)
        try:
            usage_facts = LLMTokensBillingFacts.model_validate(
                usage_payload,
                strict=True,
            )
        except ValidationError:
            usage_facts = None
        if usage_facts is not None and self._usage_exceeds_contract(
            usage_facts,
            prepared.model_contract,
        ):
            transition = await service.mark_accounting_error(
                tenant_id=prepared.context.tenant_id,
                attempt_id=attempt_id,
                expected_state="submission_started",
                settlement_billing_facts=usage_facts,
            )
        else:
            transition = await service.settle(
                tenant_id=prepared.context.tenant_id,
                attempt_id=attempt_id,
                expected_state="submission_started",
                settlement_billing_facts=(usage_facts or usage_payload),
            )
        settled_attempt = transition["attempt"]
        if settled_attempt.get("state") != "settled":
            if settled_attempt.get("state") == "accounting_error":
                raise ProviderCostContractError(
                    "provider_cost_accounting_error",
                    "LLM success usage could not be settled",
                )
            raise ProviderCostContractError(
                "provider_cost_attempt_conflict",
                "LLM cost transition did not settle",
            )
        content = getattr(response, "content", None)
        if not isinstance(content, str):
            raise ProviderCostContractError(
                "provider_cost_usage_invalid",
                "settled LLM response content is not text",
            )
        return content

    async def invoke(self, *args, **kwargs) -> str:
        """Alias for ainvoke for ergonomic await."""
        return await self.ainvoke(*args, **kwargs)

    async def invoke_json(
        self,
        system_prompt: str,
        user_message: str,
        model: str | None = None,
        *,
        operation_key: str = DEFAULT_LLM_OPERATION_KEY,
        operation_instance: str = "primary",
        max_completion_tokens: object = None,
    ) -> dict[str, Any]:
        """Call LLM asynchronously and parse JSON response.

        Routes through ainvoke with timeout protection.
        """
        raw = await self.ainvoke(
            system_prompt,
            user_message,
            model,
            operation_key=operation_key,
            operation_instance=operation_instance,
            max_completion_tokens=max_completion_tokens,
        )
        try:
            return self._parse_json(raw)
        except json.JSONDecodeError:
            # The provider mutation is already settled at this point.  Do not
            # let callers classify malformed JSON as a local fallback signal.
            raise ProviderCostContractError(
                "provider_cost_usage_invalid",
                "settled LLM response is not valid JSON",
            ) from None

    # ── Shared helpers ──

    def _parse_json(self, raw: str) -> dict[str, Any]:
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # Fallback: try to extract JSON object/array from markdown text
            import re

            # Look for JSON object or array anywhere in the text
            match = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", raw)
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    pass
            logger.error("JSON parse failed", response_length=len(raw))
            raise


async def _async_invoke(client, messages):
    """Use LangChain's native async invoke.

    `client.ainvoke` runs through httpx's async client, so asyncio.wait_for
    can actually cancel the request (cancellation propagates to httpx, which
    closes the underlying connection). The earlier `asyncio.to_thread(
    client.invoke, ...)` approach left zombie threads on timeout because
    sync httpx ignores task cancellation.
    """
    return await client.ainvoke(messages)


# Global singleton
llm = LLMClient()
