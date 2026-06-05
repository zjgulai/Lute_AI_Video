"""Static toolbox registry for dry-run productization endpoints."""

from __future__ import annotations

from src.models.toolbox_contracts import ToolboxArtifactType, ToolboxTool, ToolboxToolId

_TOOLS: dict[ToolboxToolId, ToolboxTool] = {
    ToolboxToolId.PRODUCT_IMAGE: ToolboxTool(
        tool_id=ToolboxToolId.PRODUCT_IMAGE,
        label="电商商品图",
        description="Product image set planning for ecommerce PDP, thumbnail, and hero use cases.",
        output_types=[ToolboxArtifactType.PRODUCT_IMAGE_SET],
        injectable_scenarios=["s1", "s2", "s5"],
        default_checks=["product_truth", "claim_evidence", "brand_rights"],
    ),
    ToolboxToolId.SIX_VIEW: ToolboxTool(
        tool_id=ToolboxToolId.SIX_VIEW,
        label="产品六视图",
        description="Canonical product reference manifest for downstream image and video consistency.",
        output_types=[ToolboxArtifactType.SIX_VIEW_REFERENCE_MANIFEST],
        injectable_scenarios=["s1", "s2", "s5"],
        default_checks=["canonical_six_views", "view_consistency", "reference_rights"],
    ),
    ToolboxToolId.ECOMMERCE_VISUAL: ToolboxTool(
        tool_id=ToolboxToolId.ECOMMERCE_VISUAL,
        label="电商视觉图",
        description="Commercial layout and visual pack planning for ecommerce and social channels.",
        output_types=[ToolboxArtifactType.ECOMMERCE_VISUAL_PACK],
        injectable_scenarios=["s1", "s2", "s5"],
        default_checks=["copy_safe_zone", "platform_ratio", "brand_alignment"],
    ),
    ToolboxToolId.DIGITAL_HUMAN: ToolboxTool(
        tool_id=ToolboxToolId.DIGITAL_HUMAN,
        label="数字人",
        description="Presenter demo planning with likeness and voice consent gates.",
        output_types=[ToolboxArtifactType.PRESENTER_PLAN],
        injectable_scenarios=["s1", "s2"],
        default_checks=["likeness_consent", "voice_consent", "children_safety"],
    ),
    ToolboxToolId.STORYBOARD: ToolboxTool(
        tool_id=ToolboxToolId.STORYBOARD,
        label="故事版",
        description="Storyboard package planning with shot ledger, timeline, and review checkpoints.",
        output_types=[ToolboxArtifactType.STORYBOARD_PACKAGE],
        injectable_scenarios=["s1", "s2", "s3", "s4", "s5"],
        default_checks=["shot_ledger", "timeline_floor", "review_checkpoint"],
    ),
}


def get_toolbox_tool(tool_id: ToolboxToolId) -> ToolboxTool:
    return _TOOLS[tool_id]


def list_toolbox_tools() -> list[ToolboxTool]:
    return list(_TOOLS.values())
