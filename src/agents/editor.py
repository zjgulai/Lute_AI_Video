"""Editing Agent — assemblies assets into Remotion-compatible timeline + triggers render.

Uses Remotion for actual video rendering (via Node.js bridge).
"""

import structlog

from src.models import AssetPlan, EditComposition, EditTimelineEvent, Storyboard
from src.tools.remotion_renderer import RemotionRenderer

logger = structlog.get_logger()


class EditingAgent:
    """Creates edit timeline and triggers Remotion render."""

    def __init__(self, use_mock: bool = False):
        self.use_mock = use_mock
        self.renderer = RemotionRenderer()

    async def run(
        self,
        storyboards: list[Storyboard],
        asset_plans: list[AssetPlan],
    ) -> list[EditComposition]:
        # Build asset lookup: shot_id → asset_id
        asset_lookup: dict[int, str] = {}
        for plan in asset_plans:
            for sp in plan.shot_plans:
                if sp.selected_asset_id:
                    asset_lookup[sp.shot_id] = sp.selected_asset_id

        compositions = []
        for sb in storyboards:
            timeline = []
            for shot in sb.shots:
                asset_id = asset_lookup.get(shot.id, f"placeholder-{shot.id}")
                timeline.append(
                    EditTimelineEvent(
                        shot_id=shot.id,
                        asset_id=asset_id,
                        start_time=shot.start_time,
                        end_time=shot.end_time,
                        transition="dissolve" if shot.id > 1 else "cut",
                        effects=["zoom_in"] if shot.shot_type == "hook" else [],
                    )
                )
            compositions.append(
                EditComposition(
                    script_id=sb.script_id,
                    total_duration=sb.total_duration,
                    aspect_ratio="9:16",
                    timeline=timeline,
                )
            )

        logger.info("editing: compositions built", count=len(compositions))
        return compositions

    async def render_video(self, pipeline_state: dict, output_name: str = "output.mp4") -> str:
        """Export pipeline state and trigger Remotion render.

        Args:
            pipeline_state: Complete pipeline state dict.
            output_name: Output filename.

        Returns:
            Path to the rendered .mp4 file.
        """
        # Export to JSON
        json_path = self.renderer.export_pipeline_json(pipeline_state)

        # Render (non-blocking by default — use blocking=True for sync)
        output_path = self.renderer.render(json_path, output_name, blocking=False)

        logger.info("editing: render triggered", output=str(output_path))
        return str(output_path)
