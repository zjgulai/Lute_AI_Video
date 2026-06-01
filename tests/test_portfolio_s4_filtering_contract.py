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
