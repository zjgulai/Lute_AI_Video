"""In-memory production job ledger for no-token AI video 2.0 tests."""

from __future__ import annotations

from datetime import datetime

from src.models.commercial_contracts import (
    MediaJobRecord,
    MediaJobSpec,
    MediaJobStatus,
    PromptCompileInput,
    PromptCompileResult,
)


class ProductionJobLedger:
    """Small in-memory ledger that separates generation success from delivery."""

    def __init__(self) -> None:
        self._records: dict[str, MediaJobRecord] = {}

    def prepare(self, spec: MediaJobSpec, blocked_reasons: list[str] | None = None) -> MediaJobRecord:
        blocked_reasons = blocked_reasons or []
        status = MediaJobStatus.BLOCKED if blocked_reasons else MediaJobStatus.PREPARED
        record = MediaJobRecord(
            job_id=spec.job_id,
            spec=spec,
            status=status,
            blocked_reasons=blocked_reasons,
        )
        self._records[record.job_id] = record
        return record

    def prepare_from_compile_result(
        self,
        *,
        job_id: str,
        compile_input: PromptCompileInput,
        compile_result: PromptCompileResult,
    ) -> MediaJobRecord:
        spec = MediaJobSpec(
            job_id=job_id,
            provider=compile_result.provider,
            model=compile_result.model,
            scenario=compile_input.scenario,
            step_name=compile_input.step_name,
            prompt_hash=compile_result.prompt_hash,
            prompt_compile_id=compile_result.compile_id,
            reference_asset_ids=compile_result.reference_asset_ids,
            brand_bundle_id=compile_input.brand_bundle.bundle_id,
        )
        return self.prepare(spec, blocked_reasons=compile_result.block_reasons)

    def mark_submitted(self, job_id: str, provider_job_id: str) -> MediaJobRecord:
        record = self._get(job_id)
        record.status = MediaJobStatus.SUBMITTED
        record.provider_job_id = provider_job_id
        record.updated_at = _now()
        return record

    def mark_failed(self, job_id: str, reason: str) -> MediaJobRecord:
        record = self._get(job_id)
        record.status = MediaJobStatus.FAILED
        record.failure_reason = reason
        record.delivery_accepted = False
        record.publish_allowed = False
        record.updated_at = _now()
        return record

    def mark_succeeded(self, job_id: str, artifact_paths: dict[str, str]) -> MediaJobRecord:
        record = self._get(job_id)
        record.status = MediaJobStatus.SUCCEEDED
        record.artifact_paths = artifact_paths
        record.delivery_accepted = False
        record.publish_allowed = False
        record.updated_at = _now()
        return record

    def mark_delivery_decision(self, job_id: str, *, accepted: bool, publish_allowed: bool) -> MediaJobRecord:
        if publish_allowed and not accepted:
            raise ValueError("publish_allowed requires accepted delivery")
        record = self._get(job_id)
        record.delivery_accepted = accepted
        record.publish_allowed = publish_allowed
        record.updated_at = _now()
        return record

    def get(self, job_id: str) -> MediaJobRecord | None:
        return self._records.get(job_id)

    def list_records(self) -> list[MediaJobRecord]:
        return list(self._records.values())

    def _get(self, job_id: str) -> MediaJobRecord:
        record = self._records.get(job_id)
        if record is None:
            raise KeyError(f"unknown media job id: {job_id}")
        return record


def _now() -> str:
    return datetime.utcnow().isoformat()
