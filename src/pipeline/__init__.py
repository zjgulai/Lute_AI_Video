"""Pipeline orchestrators — S2 (Brand), S3 (Remix), S4 (Live-Shoot)."""

# Import all skills to trigger auto-registration at app startup
import src.skills.video_analysis  # noqa: F401
import src.skills.remix_script  # noqa: F401
import src.skills.seedance_prompt  # noqa: F401
import src.skills.thumbnail_prompt  # noqa: F401
import src.skills.product_strategy  # noqa: F401
import src.skills.script_writer  # noqa: F401
import src.skills.brand_compliance  # noqa: F401
import src.skills.storyboard  # noqa: F401
import src.skills.viral_extractor  # noqa: F401
import src.skills.llm_skill  # noqa: F401 — base LLM skill
