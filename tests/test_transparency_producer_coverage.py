from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from src.models.transparency import validate_transparency_sidecar
from src.pipeline.scenario_config import SCENARIO_STEP_ORDERS
from src.services.transparency_provenance import (
    PRODUCER_SPECS,
    record_fast_provenance,
    record_step_provenance,
)


def _state(*, scenario: str = "s1", label: str = "s1-run") -> dict[str, Any]:
    return {
        "tenant_id": "tenant-a",
        "scenario": scenario,
        "label": label,
        "config": {
            "artifact_disposition": "pending_review",
            "c2pa_signing_mode": "local_draft",
        },
    }


def _sidecar(output_dir: Path, projection: dict[str, Any]):
    return validate_transparency_sidecar(
        output_dir / str(projection["sidecar_path"]),
        expected_sha256=str(projection["sidecar_sha256"]),
        artifact_root=output_dir,
    )


def test_producer_map_covers_every_canonical_scenario_step() -> None:
    for scenario, steps in SCENARIO_STEP_ORDERS.items():
        assert set(PRODUCER_SPECS[scenario]) == set(steps)


@pytest.mark.parametrize(
    ("step_name", "output"),
    [("compliance", None), ("thumbnail_images", [])],
)
def test_skipped_step_still_appends_explicit_simulated_provenance(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    step_name: str,
    output: object,
) -> None:
    from src import config
    from src.pipeline.step_runner import _record_step_transparency

    monkeypatch.setattr(config, "OUTPUT_DIR", tmp_path)
    state = _state()

    updated = _record_step_transparency(
        state,
        step_name=step_name,
        output=output,
        skipped=True,
    )

    assert updated == output
    sidecar = _sidecar(tmp_path, state["transparency"])
    assert len(sidecar.records) == 1
    assert sidecar.records[0].producer_step == step_name
    assert sidecar.records[0].origin_kind == "simulated"
    assert sidecar.records[0].simulated is True
    assert sidecar.records[0].artifact is None


def test_text_step_persists_hash_only_projection_and_regeneration_chain(
    tmp_path: Path,
) -> None:
    state = _state()

    first_output, first_projection = record_step_provenance(
        state=state,
        step_name="strategy",
        output={"brief": "private generated content"},
        output_dir=tmp_path,
    )
    state["transparency"] = first_projection
    second_output, second_projection = record_step_provenance(
        state=state,
        step_name="strategy",
        output={"brief": "regenerated private content"},
        output_dir=tmp_path,
    )

    assert first_output == {"brief": "private generated content"}
    assert second_output == {"brief": "regenerated private content"}
    assert first_projection["sidecar_path"] != second_projection["sidecar_path"]
    sidecar = _sidecar(tmp_path, second_projection)
    assert len(sidecar.records) == 2
    assert sidecar.records[1].parent_record_ids == (sidecar.records[0].record_id,)
    serialized = (tmp_path / str(second_projection["sidecar_path"])).read_text(
        encoding="utf-8"
    )
    assert "private generated content" not in serialized
    assert "regenerated private content" not in serialized


def test_real_media_creates_file_record_and_simulated_media_does_not(
    tmp_path: Path,
) -> None:
    real_state = _state()
    run_root = tmp_path / "tenants" / "tenant-a" / "pending_review" / "s1-run"
    clip = run_root / "clips" / "clip.mp4"
    clip.parent.mkdir(parents=True)
    clip.write_bytes(b"real-video-bytes")
    real_output = {
        "clip_paths": [str(clip)],
        "clip_details": [
            {"path": str(clip), "simulated": False, "is_stub": False}
        ],
        "simulated": False,
    }

    updated, projection = record_step_provenance(
        state=real_state,
        step_name="seedance_clips",
        output=real_output,
        output_dir=tmp_path,
    )
    real_sidecar = _sidecar(tmp_path, projection)
    file_records = [record for record in real_sidecar.records if record.artifact]
    assert updated != real_output
    assert "/transparency/artifacts/" in updated["clip_paths"][0]
    assert len(file_records) == 1
    assert file_records[0].artifact is not None
    assert "/transparency/artifacts/" in file_records[0].artifact.relative_path
    assert file_records[0].artifact.relative_path.endswith("seedance_clips-0.mp4")
    assert file_records[0].c2pa_status == "unsigned_pending_review"

    simulated_state = _state(label="s1-simulated")
    missing = (
        tmp_path
        / "tenants"
        / "tenant-a"
        / "pending_review"
        / "s1-simulated"
        / "clips"
        / "missing.mp4"
    )
    _, simulated_projection = record_step_provenance(
        state=simulated_state,
        step_name="seedance_clips",
        output={
            "clip_paths": [str(missing)],
            "clip_details": [
                {"path": str(missing), "simulated": True, "is_stub": True}
            ],
            "simulated": True,
        },
        output_dir=tmp_path,
    )
    simulated_sidecar = _sidecar(tmp_path, simulated_projection)
    assert not any(record.artifact for record in simulated_sidecar.records)
    assert any(record.simulated for record in simulated_sidecar.records)


@pytest.mark.parametrize(
    ("step_name", "suffix", "output_factory"),
    [
        (
            "keyframe_images",
            ".png",
            lambda path: {
                "shots": [
                    {
                        "keyframe_image_path": str(path),
                        "simulated": False,
                    }
                ],
                "simulated": False,
            },
        ),
        (
            "seedance_clips",
            ".mp4",
            lambda path: {
                "clip_paths": [str(path)],
                "clip_details": [
                    {
                        "path": str(path),
                        "simulated": False,
                        "is_stub": False,
                    }
                ],
                "simulated": False,
            },
        ),
    ],
)
def test_real_media_same_path_regeneration_uses_immutable_child_snapshot(
    tmp_path: Path,
    step_name: str,
    suffix: str,
    output_factory,
) -> None:
    state = _state()
    run_root = tmp_path / "tenants" / "tenant-a" / "pending_review" / "s1-run"
    mutable_path = run_root / "generated" / f"artifact{suffix}"
    mutable_path.parent.mkdir(parents=True)
    mutable_path.write_bytes(b"generation-one")

    _, first_projection = record_step_provenance(
        state=state,
        step_name=step_name,
        output=output_factory(mutable_path),
        output_dir=tmp_path,
    )
    state["transparency"] = first_projection
    mutable_path.write_bytes(b"generation-two")

    _, second_projection = record_step_provenance(
        state=state,
        step_name=step_name,
        output=output_factory(mutable_path),
        output_dir=tmp_path,
    )

    sidecar = _sidecar(tmp_path, second_projection)
    file_records = [record for record in sidecar.records if record.artifact]
    assert len(file_records) == 2
    first_artifact = file_records[0].artifact
    second_artifact = file_records[1].artifact
    assert first_artifact is not None and second_artifact is not None
    assert first_artifact.relative_path != second_artifact.relative_path
    assert (tmp_path / first_artifact.relative_path).read_bytes() == b"generation-one"
    assert (tmp_path / second_artifact.relative_path).read_bytes() == b"generation-two"
    assert file_records[1].parent_record_ids == (file_records[0].record_id,)


def test_human_edit_appends_child_without_mutating_generated_record(
    tmp_path: Path,
) -> None:
    state = _state()
    _, first_projection = record_step_provenance(
        state=state,
        step_name="scripts",
        output={"script": "generated"},
        output_dir=tmp_path,
    )
    state["transparency"] = first_projection

    _, edit_projection = record_step_provenance(
        state=state,
        step_name="scripts",
        output={"script": "human-edited"},
        output_dir=tmp_path,
        origin_kind="human_edit",
        human_edit={"script": "human-edited"},
    )

    sidecar = _sidecar(tmp_path, edit_projection)
    assert len(sidecar.records) == 2
    assert sidecar.records[0].origin_kind != "human_edit"
    assert sidecar.records[1].origin_kind == "human_edit"
    assert sidecar.records[1].parent_record_ids == (sidecar.records[0].record_id,)
    assert len(sidecar.records[1].human_edit_ids) == 1


def test_unscoped_real_media_fails_before_sidecar_publication(tmp_path: Path) -> None:
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"outside")

    try:
        record_step_provenance(
            state=_state(),
            step_name="seedance_clips",
            output={
                "clip_paths": [str(outside)],
                "clip_details": [
                    {"path": str(outside), "simulated": False, "is_stub": False}
                ],
                "simulated": False,
            },
            output_dir=tmp_path,
        )
    except ValueError as exc:
        assert "scope" in str(exc)
    else:
        raise AssertionError("unscoped real media was accepted")

    assert not list(tmp_path.rglob("transparency-sidecar.v1.*.json"))


def test_fast_no_media_records_both_generated_text_outputs(tmp_path: Path) -> None:
    result = {
        "llm_prompt": "private enhanced prompt",
        "scene_description": "private scene description",
        "video_path": "",
        "tts_path": None,
        "is_stub": False,
        "simulated": False,
    }

    updated = record_fast_provenance(
        result=result,
        tenant_id="tenant-a",
        run_id="fast-run",
        artifact_disposition="pending_review",
        c2pa_signing_mode="local_draft",
        output_dir=tmp_path,
    )

    projection = updated["transparency"]
    sidecar = _sidecar(tmp_path, projection)
    assert [record.producer_step for record in sidecar.records] == [
        "llm_prompt",
        "scene_description",
    ]
    serialized = (tmp_path / projection["sidecar_path"]).read_text(encoding="utf-8")
    assert "private enhanced prompt" not in serialized
    assert "private scene description" not in serialized


def test_required_image_signing_rebinds_output_and_records_local_readback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from src.tools.c2pa_signer import C2PASigningResult

    state = _state()
    state["config"]["c2pa_signing_mode"] = "required"
    run_root = tmp_path / "tenants" / "tenant-a" / "pending_review" / "s1-run"
    source = run_root / "keyframes" / "frame.png"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"source-image")

    def fake_sign(input_path, *, output_path, **kwargs):
        del kwargs
        destination = Path(output_path)
        destination.write_bytes(Path(input_path).read_bytes() + b"-signed")
        return C2PASigningResult(
            status="signed_local_readback",
            output_path=destination,
            manifest_sha256="a" * 64,
        )

    monkeypatch.setattr(
        "src.services.transparency_provenance.sign_and_verify_media",
        fake_sign,
    )

    updated, projection = record_step_provenance(
        state=state,
        step_name="keyframe_images",
        output={
            "shots": [
                {
                    "keyframe_image_path": str(source),
                    "simulated": False,
                }
            ],
            "simulated": False,
        },
        output_dir=tmp_path,
    )

    signed_path = Path(updated["shots"][0]["keyframe_image_path"])
    assert signed_path != source
    assert signed_path.read_bytes() == b"source-image-signed"
    sidecar = _sidecar(tmp_path, projection)
    signed_records = [record for record in sidecar.records if record.artifact]
    assert len(signed_records) == 1
    assert signed_records[0].c2pa_status == "signed_local_readback"
    signed_artifact = signed_records[0].artifact
    assert signed_artifact is not None
    assert signed_artifact.relative_path.endswith(
        "keyframe_images-0.c2pa.png"
    )


def test_required_signing_without_credentials_fails_before_sidecar(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from src.tools.c2pa_signer import C2PASigningError

    monkeypatch.delenv("C2PA_CERT_PATH", raising=False)
    monkeypatch.delenv("C2PA_KEY_PATH", raising=False)
    state = _state()
    state["config"]["c2pa_signing_mode"] = "required"
    run_root = tmp_path / "tenants" / "tenant-a" / "pending_review" / "s1-run"
    source = run_root / "keyframes" / "frame.png"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"source-image")

    with pytest.raises(C2PASigningError, match="c2pa_credentials_missing"):
        record_step_provenance(
            state=state,
            step_name="keyframe_images",
            output={
                "shots": [
                    {
                        "keyframe_image_path": str(source),
                        "simulated": False,
                    }
                ],
                "simulated": False,
            },
            output_dir=tmp_path,
        )

    assert not list(tmp_path.rglob("transparency-sidecar.v1.*.json"))
