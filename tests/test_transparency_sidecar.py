from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.models.transparency import (
    TransparencyRecordV1,
    build_file_transparency_record,
    build_inline_transparency_record,
    build_transparency_sidecar,
    validate_transparency_sidecar,
    write_transparency_sidecar,
)


def test_inline_record_is_canonical_hash_only_and_has_stable_identity() -> None:
    first = build_inline_transparency_record(
        tenant_id="tenant-a",
        scenario="s1",
        resource_id="run-a",
        producer_step="scripts",
        content_kind="text",
        content={"script": "private generated text"},
        origin_kind="provider",
        provider="deepseek",
        model="deepseek-v4-flash",
        generated_at="2026-07-22T14:00:00Z",
        parent_record_ids=(),
        simulated=False,
    )
    second = build_inline_transparency_record(
        tenant_id="tenant-a",
        scenario="s1",
        resource_id="run-a",
        producer_step="scripts",
        content_kind="text",
        content={"script": "private generated text"},
        origin_kind="provider",
        provider="deepseek",
        model="deepseek-v4-flash",
        generated_at="2026-07-22T14:00:00Z",
        parent_record_ids=(),
        simulated=False,
    )

    assert first == second
    assert first.inline_content is not None
    assert first.inline_content.sha256 == hashlib.sha256(
        b'{"script":"private generated text"}\n'
    ).hexdigest()
    serialized = json.dumps(first.model_dump(mode="json"), sort_keys=True)
    assert "private generated text" not in serialized
    assert first.ai_generated is True
    assert first.c2pa_status == "not_applicable"


@pytest.mark.parametrize(
    "generated_at",
    [
        "2026-99-99T99:99:99Z",
        "2026-02-30T14:00:00Z",
        "2026-07-22T14:00:00.1Z",
        "2026-07-22T14:00:00+00:00",
    ],
)
def test_inline_record_rejects_invalid_or_noncanonical_utc(
    generated_at: str,
) -> None:
    with pytest.raises(ValidationError, match="generated_at"):
        build_inline_transparency_record(
            tenant_id="tenant-a",
            scenario="s1",
            resource_id="run-a",
            producer_step="scripts",
            content_kind="text",
            content="hello",
            origin_kind="provider",
            provider="deepseek",
            model="deepseek-v4-flash",
            generated_at=generated_at,
            parent_record_ids=(),
            simulated=False,
        )


def test_inline_record_accepts_canonical_microsecond_utc() -> None:
    record = build_inline_transparency_record(
        tenant_id="tenant-a",
        scenario="s1",
        resource_id="run-a",
        producer_step="scripts",
        content_kind="text",
        content="hello",
        origin_kind="provider",
        provider="deepseek",
        model="deepseek-v4-flash",
        generated_at="2026-07-22T14:00:00.100000Z",
        parent_record_ids=(),
        simulated=False,
    )

    assert record.generated_at == "2026-07-22T14:00:00.100000Z"


@pytest.mark.parametrize(
    ("provider", "model"),
    [
        ("p" * 129, "model-a"),
        ("deepseek", "m" * 129),
        ("deepseek\n", "model-a"),
        ("deepseek", "model\tname"),
        ("sk-" + "a" * 32, "model-a"),
        ("deepseek", "sk-" + "a" * 32),
    ],
)
def test_provider_facts_are_bounded_safe_identifiers(
    provider: str,
    model: str,
) -> None:
    with pytest.raises(ValidationError, match="provider|model"):
        build_inline_transparency_record(
            tenant_id="tenant-a",
            scenario="s1",
            resource_id="run-a",
            producer_step="scripts",
            content_kind="text",
            content="hello",
            origin_kind="provider",
            provider=provider,
            model=model,
            generated_at="2026-07-22T14:00:00Z",
            parent_record_ids=(),
            simulated=False,
        )


@pytest.mark.parametrize(
    "override",
    [
        {"ai_generated": False},
        {"simulated": 1},
        {"generated_at": "2026-07-22 14:00:00"},
        {"record_id": "not-a-digest"},
        {"content_kind": "binary"},
        {"raw_prompt": "must never be accepted"},
    ],
)
def test_record_rejects_invalid_or_authority_like_fields(override: dict[str, object]) -> None:
    record = build_inline_transparency_record(
        tenant_id="tenant-a",
        scenario="fast",
        resource_id="run-a",
        producer_step="prompt_enhance",
        content_kind="text",
        content="hello",
        origin_kind="local",
        provider=None,
        model=None,
        generated_at="2026-07-22T14:00:00Z",
        parent_record_ids=(),
        simulated=False,
    ).model_dump(mode="json")
    record.update(override)

    with pytest.raises(ValidationError):
        TransparencyRecordV1.model_validate(record)


def test_sidecar_requires_ordered_existing_parents_and_unique_records() -> None:
    first = build_inline_transparency_record(
        tenant_id="tenant-a",
        scenario="s1",
        resource_id="run-a",
        producer_step="strategy",
        content_kind="text",
        content={"strategy": "one"},
        origin_kind="provider",
        provider="deepseek",
        model="deepseek-v4-flash",
        generated_at="2026-07-22T14:00:00Z",
        parent_record_ids=(),
        simulated=False,
    )
    child = build_inline_transparency_record(
        tenant_id="tenant-a",
        scenario="s1",
        resource_id="run-a",
        producer_step="scripts",
        content_kind="text",
        content={"script": "two"},
        origin_kind="provider",
        provider="deepseek",
        model="deepseek-v4-flash",
        generated_at="2026-07-22T14:01:00Z",
        parent_record_ids=(first.record_id,),
        simulated=False,
    )

    assert len(build_transparency_sidecar([first, child]).records) == 2
    with pytest.raises(ValueError, match="parent"):
        build_transparency_sidecar([child, first])
    with pytest.raises(ValueError, match="duplicate"):
        build_transparency_sidecar([first, first])


def test_sidecar_rejects_cross_resource_record_mix() -> None:
    first = build_inline_transparency_record(
        tenant_id="tenant-a",
        scenario="s1",
        resource_id="run-a",
        producer_step="strategy",
        content_kind="text",
        content="one",
        origin_kind="local",
        provider=None,
        model=None,
        generated_at="2026-07-22T14:00:00Z",
        parent_record_ids=(),
        simulated=False,
    )
    other = build_inline_transparency_record(
        tenant_id="tenant-a",
        scenario="s1",
        resource_id="run-b",
        producer_step="strategy",
        content_kind="text",
        content="two",
        origin_kind="local",
        provider=None,
        model=None,
        generated_at="2026-07-22T14:00:00Z",
        parent_record_ids=(),
        simulated=False,
    )

    with pytest.raises(ValueError, match="identity"):
        build_transparency_sidecar([first, other])


def test_sidecar_write_validate_and_detached_digest_fail_closed(tmp_path: Path) -> None:
    record = build_inline_transparency_record(
        tenant_id="tenant-a",
        scenario="fast",
        resource_id="run-a",
        producer_step="prompt_enhance",
        content_kind="text",
        content="hello",
        origin_kind="local",
        provider=None,
        model=None,
        generated_at="2026-07-22T14:00:00Z",
        parent_record_ids=(),
        simulated=False,
    )
    sidecar = build_transparency_sidecar([record])
    path = tmp_path / "transparency-sidecar.v1.json"

    digest = write_transparency_sidecar(path, sidecar, output_root=tmp_path)
    assert validate_transparency_sidecar(path, expected_sha256=digest) == sidecar
    assert (tmp_path / "transparency-sidecar.v1.json.sha256").is_file()

    path.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="checksum|schema"):
        validate_transparency_sidecar(path, expected_sha256=digest)


def test_file_record_binds_relative_bytes_and_detects_artifact_drift(
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "tenant-run"
    artifact = artifact_root / "video" / "final.mp4"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"fixture-video")
    record = build_file_transparency_record(
        tenant_id="tenant-a",
        scenario="s1",
        resource_id="run-a",
        producer_step="assemble_final",
        content_kind="video",
        artifact_path="video/final.mp4",
        artifact_root=artifact_root,
        origin_kind="provider",
        provider="remotion",
        model="remotion-4",
        generated_at="2026-07-22T14:02:00Z",
        parent_record_ids=(),
        simulated=False,
        c2pa_status="unsigned_pending_review",
    )
    assert record.artifact is not None
    assert record.artifact.relative_path == "video/final.mp4"
    sidecar = build_transparency_sidecar([record])
    path = artifact_root / "transparency-sidecar.v1.json"
    digest = write_transparency_sidecar(path, sidecar, output_root=artifact_root)
    assert validate_transparency_sidecar(
        path,
        expected_sha256=digest,
        artifact_root=artifact_root,
    ) == sidecar

    artifact.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="artifact bytes"):
        validate_transparency_sidecar(path, artifact_root=artifact_root)


def test_file_record_rejects_symlinked_artifact(tmp_path: Path) -> None:
    artifact_root = tmp_path / "tenant-run"
    artifact_root.mkdir()
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"outside")
    linked = artifact_root / "linked.mp4"
    linked.symlink_to(outside)

    with pytest.raises(ValueError, match="missing or unsafe"):
        build_file_transparency_record(
            tenant_id="tenant-a",
            scenario="s1",
            resource_id="run-a",
            producer_step="assemble_final",
            content_kind="video",
            artifact_path="linked.mp4",
            artifact_root=artifact_root,
            origin_kind="provider",
            provider="remotion",
            model="remotion-4",
            generated_at="2026-07-22T14:02:00Z",
            parent_record_ids=(),
            simulated=False,
            c2pa_status="unsigned_pending_review",
        )


def test_file_record_rejects_lexical_traversal_before_resolution(
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "run"
    artifact_root.mkdir()
    (artifact_root / "final.mp4").write_bytes(b"fixture-video")

    with pytest.raises(ValueError, match="canonical and relative"):
        build_file_transparency_record(
            tenant_id="tenant-a",
            scenario="s1",
            resource_id="run-a",
            producer_step="assemble_final",
            content_kind="video",
            artifact_path="../run/final.mp4",
            artifact_root=artifact_root,
            origin_kind="provider",
            provider="remotion",
            model="remotion-4",
            generated_at="2026-07-22T14:02:00Z",
            parent_record_ids=(),
            simulated=False,
            c2pa_status="unsigned_pending_review",
        )


def test_sidecar_write_rejects_symlinked_output_ancestor(tmp_path: Path) -> None:
    scoped_root = tmp_path / "scope"
    scoped_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (scoped_root / "link").symlink_to(outside, target_is_directory=True)
    record = build_inline_transparency_record(
        tenant_id="tenant-a",
        scenario="fast",
        resource_id="run-a",
        producer_step="prompt_enhance",
        content_kind="text",
        content="hello",
        origin_kind="local",
        provider=None,
        model=None,
        generated_at="2026-07-22T14:00:00Z",
        parent_record_ids=(),
        simulated=False,
    )
    sidecar = build_transparency_sidecar([record])
    destination = scoped_root / "link" / "nested" / "transparency-sidecar.v1.json"

    with pytest.raises(ValueError, match="unsafe"):
        write_transparency_sidecar(
            destination,
            sidecar,
            output_root=scoped_root,
        )

    assert not (outside / "nested" / "transparency-sidecar.v1.json").exists()
