"""Append-only provenance capture for Fast and scenario producer outputs."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, Literal, cast

from src.models.transparency import (
    C2PAStatus,
    ContentKind,
    SigningMode,
    TransparencyProjectionV1,
    TransparencyRecordV1,
    build_file_transparency_record,
    build_inline_transparency_record,
    build_transparency_sidecar,
    transparency_sidecar_sha256,
    validate_transparency_sidecar,
    write_transparency_sidecar,
)
from src.pipeline.model_router import select_model
from src.pipeline.scenario_config import SCENARIO_STEP_ORDERS
from src.tools.c2pa_signer import (
    C2PASigningPolicy,
    C2PASigningResult,
    sign_and_verify_media,
    verify_signed_media_readback,
)

_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_MEDIA_KINDS = frozenset({"image", "audio", "video"})
Scenario = Literal["fast", "s1", "s2", "s3", "s4", "s5"]


@dataclass(frozen=True)
class ProducerSpec:
    content_kind: Literal["text", "image", "audio", "video"]
    upstream_steps: tuple[str, ...] = ()


def _specs(
    ordered: tuple[tuple[str, ContentKind, tuple[str, ...]], ...],
) -> Mapping[str, ProducerSpec]:
    return MappingProxyType(
        {
            step: ProducerSpec(content_kind=kind, upstream_steps=upstream)
            for step, kind, upstream in ordered
        }
    )


PRODUCER_SPECS: Mapping[str, Mapping[str, ProducerSpec]] = MappingProxyType(
    {
        "s1": _specs(
            (
                ("strategy", "text", ()),
                ("scripts", "text", ("strategy",)),
                ("compliance", "text", ("scripts",)),
                ("storyboards", "text", ("strategy", "scripts")),
                ("continuity_storyboard_grid", "text", ("storyboards",)),
                ("keyframe_images", "image", ("continuity_storyboard_grid",)),
                ("video_prompts", "text", ("continuity_storyboard_grid", "keyframe_images")),
                ("thumbnail_prompts", "text", ("scripts", "storyboards")),
                ("seedance_clips", "video", ("video_prompts", "keyframe_images")),
                ("tts_audio", "audio", ("scripts",)),
                ("thumbnail_images", "image", ("thumbnail_prompts",)),
                ("assemble_final", "video", ("seedance_clips", "tts_audio", "thumbnail_images")),
                ("audit", "text", ("assemble_final",)),
            )
        ),
        "s2": _specs(
            (
                ("strategy", "text", ()),
                ("scripts", "text", ("strategy",)),
                ("compliance", "text", ("scripts",)),
                ("storyboards", "text", ("strategy", "scripts")),
                ("continuity_storyboard_grid", "text", ("storyboards",)),
                ("keyframe_images", "image", ("continuity_storyboard_grid",)),
                ("video_prompts", "text", ("continuity_storyboard_grid", "keyframe_images")),
                ("thumbnail_prompts", "text", ("scripts", "storyboards")),
                ("seedance_clips", "video", ("video_prompts", "keyframe_images")),
                ("tts_audio", "audio", ("scripts",)),
                ("thumbnail_images", "image", ("thumbnail_prompts",)),
                ("assemble_final", "video", ("seedance_clips", "tts_audio", "thumbnail_images")),
                ("audit", "text", ("assemble_final",)),
            )
        ),
        "s3": _specs(
            (
                ("video_analysis", "text", ()),
                ("character_identity", "text", ("video_analysis",)),
                ("remix_script", "text", ("video_analysis", "character_identity")),
                ("storyboards", "text", ("remix_script",)),
                ("continuity_storyboard_grid", "text", ("storyboards",)),
                ("keyframe_images", "image", ("continuity_storyboard_grid",)),
                ("video_prompts", "text", ("continuity_storyboard_grid", "keyframe_images")),
                ("thumbnail_prompts", "text", ("remix_script", "storyboards")),
                ("seedance_clips", "video", ("video_prompts", "keyframe_images")),
                ("tts_audio", "audio", ("remix_script",)),
                ("thumbnail_images", "image", ("thumbnail_prompts",)),
                ("assemble_final", "video", ("seedance_clips", "tts_audio", "thumbnail_images")),
                ("audit", "text", ("assemble_final",)),
            )
        ),
        "s4": _specs(
            (
                ("scripts", "text", ()),
                ("continuity_storyboard_grid", "text", ("scripts",)),
                ("video_prompts", "text", ("continuity_storyboard_grid",)),
                ("thumbnails", "text", ("scripts", "continuity_storyboard_grid")),
                ("seedance_clips", "video", ("video_prompts",)),
                ("tts_audio", "audio", ("scripts",)),
                ("assemble_final", "video", ("seedance_clips", "tts_audio")),
                ("audit", "text", ("assemble_final",)),
            )
        ),
        "s5": _specs(
            (
                ("vlog_strategy", "text", ()),
                ("continuity_storyboard_grid", "text", ("vlog_strategy",)),
                ("video_prompts", "text", ("continuity_storyboard_grid",)),
                ("seedance_clips", "video", ("video_prompts",)),
                ("tts_audio", "audio", ("vlog_strategy",)),
                ("assemble_final", "video", ("seedance_clips", "tts_audio")),
                ("audit", "text", ("assemble_final",)),
            )
        ),
    }
)


def _canonical_digest(value: object) -> str:
    try:
        payload = (
            json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("transparency content is not canonical JSON") from exc
    return hashlib.sha256(payload).hexdigest()


def _required_identity(state: Mapping[str, Any], key: str) -> str:
    value = state.get(key)
    if not isinstance(value, str) or _SAFE_ID_RE.fullmatch(value) is None:
        raise ValueError(f"transparency {key} is invalid")
    return value


def _run_scope(
    state: Mapping[str, Any], output_dir: Path
) -> tuple[str, Scenario, str, SigningMode, PurePosixPath]:
    tenant_id = _required_identity(state, "tenant_id")
    scenario = state.get("scenario")
    if scenario not in PRODUCER_SPECS:
        raise ValueError("transparency scenario is invalid")
    resource_id = _required_identity(state, "label")
    config = state.get("config")
    if not isinstance(config, Mapping):
        raise ValueError("transparency state config is invalid")
    disposition = config.get("artifact_disposition")
    if disposition not in {"pending_review", "quarantine"}:
        raise ValueError("transparency artifact disposition is invalid")
    signing_mode = config.get("c2pa_signing_mode")
    if signing_mode not in {"local_draft", "required"}:
        raise ValueError("transparency signing mode is invalid")
    if output_dir.is_symlink() or not output_dir.is_dir():
        raise ValueError("transparency output root is missing or unsafe")
    relative_run_root = PurePosixPath(
        "tenants", tenant_id, disposition, resource_id
    )
    return (
        tenant_id,
        cast(Scenario, scenario),
        resource_id,
        cast(SigningMode, signing_mode),
        relative_run_root,
    )


def _prior_records(
    state: Mapping[str, Any],
    *,
    output_dir: Path,
    relative_run_root: PurePosixPath,
) -> list[TransparencyRecordV1]:
    raw = state.get("transparency")
    if raw is None:
        return []
    projection = TransparencyProjectionV1.model_validate(raw)
    expected_prefix = relative_run_root / "transparency"
    projected = PurePosixPath(projection.sidecar_path)
    if projected.parent != expected_prefix:
        raise ValueError("transparency projection is outside its run scope")
    sidecar = validate_transparency_sidecar(
        output_dir.joinpath(*projected.parts),
        expected_sha256=projection.sidecar_sha256,
        artifact_root=output_dir,
    )
    if len(sidecar.records) != projection.record_count:
        raise ValueError("transparency projection record count is inconsistent")
    return list(sidecar.records)


def _latest_record_ids(
    records: list[TransparencyRecordV1], producer_steps: tuple[str, ...]
) -> tuple[str, ...]:
    wanted = set(producer_steps)
    latest: dict[str, str] = {}
    for record in records:
        base_step = record.producer_step.removesuffix(".metadata")
        if base_step in wanted:
            latest[base_step] = record.record_id
    return tuple(latest[step] for step in producer_steps if step in latest)


def _parent_ids(
    records: list[TransparencyRecordV1], producer_step: str
) -> tuple[str, ...]:
    for record in reversed(records):
        if record.producer_step == producer_step:
            return (record.record_id,)
    return ()


def _flatten_paths(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, (list, tuple)):
        return [item for item in value if isinstance(item, str) and item]
    return []


def _media_paths(step_name: str, output: Any) -> list[str]:
    if step_name == "keyframe_images":
        if isinstance(output, (list, tuple)):
            paths: list[str] = []
            for item in output:
                paths.extend(_media_paths(step_name, item))
            return list(dict.fromkeys(paths))
        if not isinstance(output, Mapping):
            return []
        paths: list[str] = []
        paths.extend(_flatten_paths(output.get("keyframe_image_path")))
        shots = output.get("shots")
        if isinstance(shots, list):
            for shot in shots:
                if isinstance(shot, Mapping):
                    paths.extend(_flatten_paths(shot.get("keyframe_image_path")))
        paths.extend(_flatten_paths(output.get("image_paths")))
        return list(dict.fromkeys(paths))
    if step_name == "thumbnail_images":
        if isinstance(output, Mapping):
            return list(dict.fromkeys(_flatten_paths(output.get("image_paths"))))
        return list(dict.fromkeys(_flatten_paths(output)))
    if step_name == "seedance_clips":
        if not isinstance(output, Mapping):
            return list(dict.fromkeys(_flatten_paths(output)))
        return list(
            dict.fromkeys(
                _flatten_paths(output.get("clip_paths"))
                or _flatten_paths(output.get("clips"))
            )
        )
    if step_name == "tts_audio":
        if isinstance(output, Mapping):
            return list(dict.fromkeys(_flatten_paths(output.get("audio_paths"))))
        return list(dict.fromkeys(_flatten_paths(output)))
    if step_name == "assemble_final":
        if isinstance(output, Mapping):
            return _flatten_paths(output.get("video_path"))
        if isinstance(output, (list, tuple)) and output:
            return _flatten_paths(output[0])
    return []


def _exact_real_media(step_name: str, output: Any) -> bool:
    if isinstance(output, (list, tuple)):
        return bool(output) and all(_exact_real_media(step_name, item) for item in output)
    if not isinstance(output, Mapping):
        return False
    simulated = output.get("simulated")
    if step_name == "assemble_final":
        return simulated is False and output.get("is_stub") is False
    if simulated is not False:
        return False
    if step_name == "seedance_clips":
        details = output.get("clip_details")
        if not isinstance(details, list) or not details:
            return False
        return all(
            isinstance(item, Mapping)
            and item.get("simulated") is False
            and item.get("is_stub") is False
            for item in details
        )
    return True


def _media_origin(
    scenario: Scenario, step_name: str
) -> tuple[Literal["provider", "local"], str | None, str | None]:
    if step_name in {"keyframe_images", "thumbnail_images"}:
        return "provider", "poyo", "gpt-image-2"
    if step_name == "seedance_clips":
        return "provider", "poyo", select_model(scenario)
    if step_name == "tts_audio":
        return "provider", "siliconflow", "FunAudioLLM/CosyVoice2-0.5B"
    return "local", None, None


def _relative_scoped_artifact(
    raw_path: str,
    *,
    output_dir: Path,
    relative_run_root: PurePosixPath,
) -> str:
    candidate = Path(raw_path)
    root = output_dir.resolve(strict=True)
    resolved = candidate.resolve(strict=True) if candidate.is_absolute() else (root / candidate).resolve(strict=True)
    try:
        relative = resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError("transparency artifact is outside output scope") from exc
    pure = PurePosixPath(relative.as_posix())
    if not pure.is_relative_to(relative_run_root):
        raise ValueError("transparency artifact is outside run scope")
    return pure.as_posix()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _immutable_media_snapshot(
    raw_path: str,
    *,
    output_dir: Path,
    relative_run_root: PurePosixPath,
    producer_step: str,
    index: int,
) -> str:
    """Copy mutable producer output into a content-addressed no-clobber path."""

    relative_source = PurePosixPath(
        _relative_scoped_artifact(
            raw_path,
            output_dir=output_dir,
            relative_run_root=relative_run_root,
        )
    )
    root = output_dir.resolve(strict=True)
    source = root.joinpath(*relative_source.parts)
    if source.is_symlink() or not source.is_file() or source.stat().st_size <= 0:
        raise ValueError("transparency artifact is missing or unsafe")
    probe = root
    for part in relative_source.parts:
        probe = probe / part
        if probe.is_symlink():
            raise ValueError("transparency artifact is missing or unsafe")
    digest = _sha256_file(source)
    suffix = source.suffix.lower()
    snapshot_relative = (
        relative_run_root
        / "transparency"
        / "artifacts"
        / digest
        / f"{producer_step}-{index}{suffix}"
    )
    snapshot = root.joinpath(*snapshot_relative.parts)
    if source == snapshot:
        return snapshot_relative.as_posix()
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    if snapshot.parent.is_symlink():
        raise ValueError("transparency snapshot path is unsafe")
    if not snapshot.exists():
        fd, temp_name = tempfile.mkstemp(
            prefix=f".{snapshot.name}.",
            suffix=".partial",
            dir=snapshot.parent,
        )
        temporary = Path(temp_name)
        try:
            with os.fdopen(fd, "wb") as target, source.open("rb") as source_handle:
                for chunk in iter(lambda: source_handle.read(1024 * 1024), b""):
                    target.write(chunk)
                target.flush()
                os.fsync(target.fileno())
            if _sha256_file(temporary) != digest:
                raise ValueError("transparency snapshot digest is inconsistent")
            try:
                os.link(temporary, snapshot)
            except FileExistsError:
                if not snapshot.exists():
                    raise ValueError(
                        "transparency snapshot publication is inconsistent"
                    ) from None
        finally:
            temporary.unlink(missing_ok=True)
    if (
        snapshot.is_symlink()
        or not snapshot.is_file()
        or snapshot.stat().st_size <= 0
        or _sha256_file(snapshot) != digest
    ):
        raise ValueError("transparency snapshot is inconsistent")
    return snapshot_relative.as_posix()


def _media_format(path: Path) -> str:
    suffix = path.suffix.lower()
    formats = {
        ".mp4": "video/mp4",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }
    try:
        return formats[suffix]
    except KeyError as exc:
        raise ValueError("transparency media format is unsupported") from exc


def _sign_scoped_media(
    *,
    source: Path,
    scenario: str,
    producer_step: str,
    resource_id: str,
    signing_mode: Literal["local_draft", "required"],
) -> C2PASigningResult:
    destination = source.with_name(f"{source.stem}.c2pa{source.suffix.lower()}")
    return sign_and_verify_media(
        source,
        output_path=destination,
        title=f"{scenario}:{producer_step}:{resource_id}",
        policy=C2PASigningPolicy(mode=signing_mode),
        certificate_path=os.environ.get("C2PA_CERT_PATH"),
        private_key_path=os.environ.get("C2PA_KEY_PATH"),
        timestamp_authority_url=os.environ.get(
            "C2PA_TSA_URL",
            "http://timestamp.digicert.com",
        ),
        media_format=_media_format(source),
    )


def _replace_output_paths(value: Any, replacements: Mapping[str, str]) -> Any:
    if isinstance(value, str):
        return replacements.get(value, value)
    if isinstance(value, list):
        return [_replace_output_paths(item, replacements) for item in value]
    if isinstance(value, tuple):
        return tuple(_replace_output_paths(item, replacements) for item in value)
    if isinstance(value, dict):
        return {
            key: _replace_output_paths(item, replacements)
            for key, item in value.items()
        }
    return value


def record_step_provenance(
    *,
    state: Mapping[str, Any],
    step_name: str,
    output: Any,
    output_dir: Path,
    origin_kind: Literal["local", "human_edit", "simulated"] = "local",
    human_edit: Any | None = None,
) -> tuple[Any, dict[str, Any]]:
    """Append one completed producer result and publish a new sidecar snapshot."""

    output_dir = Path(output_dir).resolve()
    tenant_id, scenario, resource_id, signing_mode, relative_run_root = _run_scope(
        state, output_dir
    )
    updated_output = copy.deepcopy(output)
    spec = PRODUCER_SPECS[scenario].get(step_name)
    if spec is None:
        raise ValueError("transparency producer step is not reviewed")
    prior = _prior_records(
        state,
        output_dir=output_dir,
        relative_run_root=relative_run_root,
    )
    generated_at = datetime.now(UTC).isoformat(
        timespec="microseconds"
    ).replace("+00:00", "Z")
    source_ids = _latest_record_ids(prior, spec.upstream_steps)
    human_edit_ids = (
        (_canonical_digest(human_edit),) if origin_kind == "human_edit" else ()
    )
    new_records: list[TransparencyRecordV1] = []

    paths = _media_paths(step_name, updated_output)
    exact_real = (
        origin_kind != "simulated"
        and bool(paths)
        and _exact_real_media(step_name, updated_output)
    )

    if spec.content_kind == "text" or not exact_real:
        inline_origin = (
            origin_kind
            if spec.content_kind == "text" or origin_kind == "human_edit"
            else "simulated"
        )
        new_records.append(
            build_inline_transparency_record(
                tenant_id=tenant_id,
                scenario=scenario,
                resource_id=resource_id,
                producer_step=step_name,
                content_kind=spec.content_kind,
                content=updated_output,
                origin_kind=inline_origin,
                provider=None,
                model=None,
                generated_at=generated_at,
                parent_record_ids=_parent_ids(prior, step_name),
                source_record_ids=source_ids,
                human_edit_ids=human_edit_ids,
                simulated=spec.content_kind != "text" or origin_kind == "simulated",
            )
        )
    else:
        c2pa_statuses: dict[str, C2PAStatus] = {}
        replacements: dict[str, str] = {}
        for index, path in enumerate(paths):
            snapshot_relative = _immutable_media_snapshot(
                path,
                output_dir=output_dir,
                relative_run_root=relative_run_root,
                producer_step=step_name,
                index=index,
            )
            snapshot = output_dir.joinpath(*PurePosixPath(snapshot_relative).parts)
            final_path = snapshot
            c2pa_status: C2PAStatus = "not_applicable"
            if spec.content_kind in {"image", "video"}:
                destination = snapshot.with_name(
                    f"{snapshot.stem}.c2pa{snapshot.suffix.lower()}"
                )
                if signing_mode == "required" and destination.exists():
                    verify_signed_media_readback(
                        destination,
                        media_format=_media_format(destination),
                    )
                    signing_result = C2PASigningResult(
                        "signed_local_readback",
                        destination,
                        None,
                    )
                else:
                    signing_result = _sign_scoped_media(
                        source=snapshot,
                        scenario=scenario,
                        producer_step=step_name,
                        resource_id=resource_id,
                        signing_mode=signing_mode,
                    )
                final_path = signing_result.output_path
                c2pa_status = signing_result.status
            replacements[path] = str(final_path)
            c2pa_statuses[str(final_path)] = c2pa_status
        updated_output = _replace_output_paths(updated_output, replacements)
        paths = _media_paths(step_name, updated_output)
        metadata_step = f"{step_name}.metadata"
        metadata_origin = "human_edit" if origin_kind == "human_edit" else "local"
        metadata = build_inline_transparency_record(
            tenant_id=tenant_id,
            scenario=scenario,
            resource_id=resource_id,
            producer_step=metadata_step,
            content_kind="text",
            content=updated_output,
            origin_kind=metadata_origin,
            provider=None,
            model=None,
            generated_at=generated_at,
            parent_record_ids=_parent_ids(prior, metadata_step),
            source_record_ids=source_ids,
            human_edit_ids=human_edit_ids,
            simulated=False,
        )
        new_records.append(metadata)
        if origin_kind == "human_edit":
            media_origin, provider, model = "human_edit", None, None
        else:
            media_origin, provider, model = _media_origin(scenario, step_name)
        file_sources = tuple(dict.fromkeys((*source_ids, metadata.record_id)))
        for path in paths:
            relative_path = _relative_scoped_artifact(
                path,
                output_dir=output_dir,
                relative_run_root=relative_run_root,
            )
            new_records.append(
                build_file_transparency_record(
                    tenant_id=tenant_id,
                    scenario=scenario,
                    resource_id=resource_id,
                    producer_step=step_name,
                    content_kind=spec.content_kind,
                    artifact_path=relative_path,
                    artifact_root=output_dir,
                    origin_kind=media_origin,
                    provider=provider,
                    model=model,
                    generated_at=generated_at,
                    parent_record_ids=_parent_ids(prior, step_name),
                    source_record_ids=file_sources,
                    human_edit_ids=human_edit_ids,
                    simulated=False,
                    c2pa_status=c2pa_statuses[path],
                )
            )

    sidecar = build_transparency_sidecar([*prior, *new_records])
    digest = transparency_sidecar_sha256(sidecar)
    relative_sidecar = (
        relative_run_root
        / "transparency"
        / f"transparency-sidecar.v1.{digest}.json"
    )
    sidecar_path = output_dir.joinpath(*relative_sidecar.parts)
    if sidecar_path.exists():
        validate_transparency_sidecar(
            sidecar_path,
            expected_sha256=digest,
            artifact_root=output_dir,
        )
    else:
        written_digest = write_transparency_sidecar(
            sidecar_path,
            sidecar,
            output_root=output_dir,
        )
        if written_digest != digest:
            raise ValueError("transparency sidecar digest is inconsistent")

    final_record = next(
        (
            record
            for record in reversed(new_records)
            if step_name == "assemble_final" and record.artifact is not None
        ),
        None,
    )
    projection = TransparencyProjectionV1(
        sidecar_path=relative_sidecar.as_posix(),
        sidecar_sha256=digest,
        record_count=len(sidecar.records),
        c2pa_signing_mode=signing_mode,
        final_artifact_record_id=(final_record.record_id if final_record else None),
        final_artifact_c2pa_status=(final_record.c2pa_status if final_record else None),
    )
    return updated_output, projection.model_dump(mode="json")


def record_fast_provenance(
    *,
    result: Mapping[str, Any],
    tenant_id: str,
    run_id: str,
    artifact_disposition: Literal["pending_review", "quarantine"],
    c2pa_signing_mode: Literal["local_draft", "required"],
    output_dir: Path,
) -> dict[str, Any]:
    """Attach one immutable provenance projection to a Fast result."""

    if _SAFE_ID_RE.fullmatch(tenant_id) is None or _SAFE_ID_RE.fullmatch(run_id) is None:
        raise ValueError("Fast transparency identity is invalid")
    output_dir = Path(output_dir).resolve()
    if output_dir.is_symlink() or not output_dir.is_dir():
        raise ValueError("transparency output root is missing or unsafe")
    relative_run_root = PurePosixPath(
        "tenants",
        tenant_id,
        artifact_disposition,
        "fast_mode",
        run_id,
    )
    generated_at = datetime.now(UTC).isoformat(
        timespec="microseconds"
    ).replace("+00:00", "Z")
    updated_result = dict(result)
    records: list[TransparencyRecordV1] = []
    for step_name in ("llm_prompt", "scene_description"):
        value = updated_result.get(step_name)
        if not isinstance(value, str):
            raise ValueError(f"Fast transparency {step_name} is invalid")
        records.append(
            build_inline_transparency_record(
                tenant_id=tenant_id,
                scenario="fast",
                resource_id=run_id,
                producer_step=step_name,
                content_kind="text",
                content=value,
                origin_kind="local",
                provider=None,
                model=None,
                generated_at=generated_at,
                parent_record_ids=(),
                simulated=False,
            )
        )

    source_ids = tuple(record.record_id for record in records)
    final_record: TransparencyRecordV1 | None = None
    video_path = updated_result.get("video_path")
    is_stub = updated_result.get("is_stub")
    simulated = updated_result.get("simulated")
    if isinstance(video_path, str) and video_path and is_stub is False and simulated is False:
        relative_video = _relative_scoped_artifact(
            video_path,
            output_dir=output_dir,
            relative_run_root=relative_run_root,
        )
        signing_result = _sign_scoped_media(
            source=output_dir.joinpath(*PurePosixPath(relative_video).parts),
            scenario="fast",
            producer_step="video",
            resource_id=run_id,
            signing_mode=c2pa_signing_mode,
        )
        signed_relative_video = _relative_scoped_artifact(
            str(signing_result.output_path),
            output_dir=output_dir,
            relative_run_root=relative_run_root,
        )
        updated_result["video_path"] = signed_relative_video
        updated_result["video_url"] = signed_relative_video
        updated_result["filename"] = signing_result.output_path.name
        final_record = build_file_transparency_record(
            tenant_id=tenant_id,
            scenario="fast",
            resource_id=run_id,
            producer_step="video",
            content_kind="video",
            artifact_path=signed_relative_video,
            artifact_root=output_dir,
            origin_kind="provider",
            provider="poyo",
            model=select_model("s1"),
            generated_at=generated_at,
            parent_record_ids=(),
            source_record_ids=source_ids,
            simulated=False,
            c2pa_status=signing_result.status,
        )
        records.append(final_record)
    elif is_stub is True or simulated is True:
        records.append(
            build_inline_transparency_record(
                tenant_id=tenant_id,
                scenario="fast",
                resource_id=run_id,
                producer_step="video",
                content_kind="video",
                content={"is_stub": is_stub, "simulated": simulated},
                origin_kind="simulated",
                provider=None,
                model=None,
                generated_at=generated_at,
                parent_record_ids=(),
                source_record_ids=source_ids,
                simulated=True,
            )
        )

    tts_path = updated_result.get("tts_path")
    if isinstance(tts_path, str) and tts_path:
        tts_fallback = updated_result.get("tts_is_fallback")
        if tts_fallback is False and simulated is False:
            relative_tts = _relative_scoped_artifact(
                tts_path,
                output_dir=output_dir,
                relative_run_root=relative_run_root,
            )
            records.append(
                build_file_transparency_record(
                    tenant_id=tenant_id,
                    scenario="fast",
                    resource_id=run_id,
                    producer_step="tts_audio",
                    content_kind="audio",
                    artifact_path=relative_tts,
                    artifact_root=output_dir,
                    origin_kind="provider",
                    provider="siliconflow",
                    model="FunAudioLLM/CosyVoice2-0.5B",
                    generated_at=generated_at,
                    parent_record_ids=(),
                    source_record_ids=(records[1].record_id,),
                    simulated=False,
                    c2pa_status="not_applicable",
                )
            )
        else:
            records.append(
                build_inline_transparency_record(
                    tenant_id=tenant_id,
                    scenario="fast",
                    resource_id=run_id,
                    producer_step="tts_audio",
                    content_kind="audio",
                    content={"is_fallback": tts_fallback},
                    origin_kind="simulated",
                    provider=None,
                    model=None,
                    generated_at=generated_at,
                    parent_record_ids=(),
                    source_record_ids=(records[1].record_id,),
                    simulated=True,
                )
            )

    sidecar = build_transparency_sidecar(records)
    digest = transparency_sidecar_sha256(sidecar)
    relative_sidecar = (
        relative_run_root
        / "transparency"
        / f"transparency-sidecar.v1.{digest}.json"
    )
    sidecar_path = output_dir.joinpath(*relative_sidecar.parts)
    if sidecar_path.exists():
        validate_transparency_sidecar(
            sidecar_path,
            expected_sha256=digest,
            artifact_root=output_dir,
        )
    else:
        written_digest = write_transparency_sidecar(
            sidecar_path,
            sidecar,
            output_root=output_dir,
        )
        if written_digest != digest:
            raise ValueError("transparency sidecar digest is inconsistent")

    projection = TransparencyProjectionV1(
        sidecar_path=relative_sidecar.as_posix(),
        sidecar_sha256=digest,
        record_count=len(records),
        c2pa_signing_mode=c2pa_signing_mode,
        final_artifact_record_id=(final_record.record_id if final_record else None),
        final_artifact_c2pa_status=(final_record.c2pa_status if final_record else None),
    )
    updated_result["transparency"] = projection.model_dump(mode="json")
    return updated_result


def validate_producer_specs() -> None:
    """Fail import-time tests when the reviewed map drifts from canonical steps."""

    if set(PRODUCER_SPECS) != set(SCENARIO_STEP_ORDERS):
        raise ValueError("transparency scenario producer map is incomplete")
    for scenario, steps in SCENARIO_STEP_ORDERS.items():
        if set(PRODUCER_SPECS[scenario]) != set(steps):
            raise ValueError(f"transparency producer map is incomplete for {scenario}")


validate_producer_specs()


__all__ = [
    "PRODUCER_SPECS",
    "ProducerSpec",
    "record_fast_provenance",
    "record_step_provenance",
]
