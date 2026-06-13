"""S4 portfolio filtering contract for /works and /library.

The frontend splits generated media by portfolio `kind`: /works consumes
`final_work`, while /library Materials consumes `creation_intermediate`.
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_s4_final_work_and_intermediate_assets_stay_separated(tmp_path, monkeypatch):
    import src.routers.portfolio as portfolio_mod

    output_dir = tmp_path / "output"
    renders = output_dir / "renders"
    seedance = output_dir / "seedance"
    renders.mkdir(parents=True)
    seedance.mkdir(parents=True)

    final_video = renders / "live_shoot_1700000000.mp4"
    intermediate_clip = seedance / "live_shoot_1700000000_clip_1.mp4"
    final_video.write_bytes(b"0" * (1024 * 1024 + 1))
    intermediate_clip.write_bytes(b"1" * (1024 * 1024 + 1))

    monkeypatch.setattr(portfolio_mod, "OUTPUT_DIR", output_dir)
    monkeypatch.setattr(
        portfolio_mod,
        "THUMBNAIL_DIR",
        output_dir / "thumbnails" / "portfolio_posters",
    )
    portfolio_mod._CACHE.clear()
    portfolio_mod._VIEW_CACHE.clear()

    final_resp = await portfolio_mod.list_portfolio(kind="final_work", limit=10)
    intermediate_resp = await portfolio_mod.list_portfolio(kind="creation_intermediate", limit=10)

    assert [item.id for item in final_resp.files] == ["renders/live_shoot_1700000000.mp4"]
    assert final_resp.files[0].category == "renders"
    assert final_resp.files[0].kind == "final_work"

    assert [item.id for item in intermediate_resp.files] == ["seedance/live_shoot_1700000000_clip_1.mp4"]
    assert intermediate_resp.files[0].category == "seedance"
    assert intermediate_resp.files[0].kind == "creation_intermediate"


@pytest.mark.asyncio
async def test_pending_review_assets_are_library_materials_not_final_work(tmp_path, monkeypatch):
    import src.routers.portfolio as portfolio_mod

    output_dir = tmp_path / "output"
    pending = output_dir / "pending_review" / "momcozy_sterilizer_smoke_20260607"
    pending.mkdir(parents=True)
    pending_image = pending / "main_45.png"
    pending_video = pending / "i2v_15s.mp4"
    pending_image.write_bytes(b"i" * (1024 * 1024 + 1))
    pending_video.write_bytes(b"v" * (1024 * 1024 + 1))

    monkeypatch.setattr(portfolio_mod, "OUTPUT_DIR", output_dir)
    monkeypatch.setattr(
        portfolio_mod,
        "THUMBNAIL_DIR",
        output_dir / "thumbnails" / "portfolio_posters",
    )
    portfolio_mod._CACHE.clear()
    portfolio_mod._VIEW_CACHE.clear()

    final_resp = await portfolio_mod.list_portfolio(kind="final_work", limit=10)
    intermediate_resp = await portfolio_mod.list_portfolio(kind="creation_intermediate", limit=10)

    assert final_resp.files == []
    assert {item.id for item in intermediate_resp.files} == {
        "pending_review/momcozy_sterilizer_smoke_20260607/main_45.png",
        "pending_review/momcozy_sterilizer_smoke_20260607/i2v_15s.mp4",
    }
    assert {item.category for item in intermediate_resp.files} == {"pending_review"}
    assert {item.kind for item in intermediate_resp.files} == {"creation_intermediate"}
    assert {item.review_status for item in intermediate_resp.files} == {"pending_review"}


@pytest.mark.asyncio
async def test_portfolio_posters_are_thumbnail_refs_not_independent_assets(tmp_path, monkeypatch):
    import src.routers.portfolio as portfolio_mod

    output_dir = tmp_path / "output"
    run_label = "l4d5s_s2_bounded_transport_contract"
    pending = output_dir / "tenants" / "momcozy-marketing" / "pending_review" / run_label / "clips"
    poster_dir = output_dir / "thumbnails" / "portfolio_posters"
    pending.mkdir(parents=True)
    poster_dir.mkdir(parents=True)

    video = pending / "seedance_contract.mp4"
    video.write_bytes(b"v" * (1024 * 1024 + 1))
    poster = poster_dir / (
        "tenants__momcozy-marketing__pending_review__"
        f"{run_label}__clips__seedance_contract.jpg"
    )
    poster.write_bytes(b"p" * (1024 * 1024 + 1))

    monkeypatch.setattr(portfolio_mod, "OUTPUT_DIR", output_dir)
    monkeypatch.setattr(portfolio_mod, "THUMBNAIL_DIR", poster_dir)
    portfolio_mod._CACHE.clear()
    portfolio_mod._VIEW_CACHE.clear()

    intermediate_resp = await portfolio_mod.list_portfolio(kind="creation_intermediate", limit=10)

    assert [item.path for item in intermediate_resp.files] == [
        f"tenants/momcozy-marketing/pending_review/{run_label}/clips/seedance_contract.mp4"
    ]
    assert intermediate_resp.files[0].category == "pending_review"
    assert intermediate_resp.files[0].kind == "creation_intermediate"
    assert intermediate_resp.files[0].tenant_id == "momcozy-marketing"
    assert intermediate_resp.files[0].review_status == "pending_review"
    assert intermediate_resp.files[0].thumbnail_path == (
        "thumbnails/portfolio_posters/tenants__momcozy-marketing__pending_review__"
        f"{run_label}__clips__seedance_contract.jpg"
    )
