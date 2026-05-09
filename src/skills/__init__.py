"""Skills framework for AI_vedio pipeline.

Skills replace direct LLM calls in pipeline nodes.
Each skill encapsulates: prompt template + retry logic + output validation + fallback.

Key components:
- SkillCallable: abstract base class for all skills
- SkillRegistry: central registry for skill discovery and execution
- LLMSkill: concrete implementation for LLM-based generation skills
- SkillResult: standardized output envelope
"""

from src.skills.base import SkillCallable, SkillResult
from src.skills.llm_skill import LLMSkill
from src.skills.registry import SkillRegistry

__all__ = ["SkillCallable", "SkillResult", "SkillRegistry", "LLMSkill"]
