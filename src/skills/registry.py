"""SkillRegistry — central registry for all pipeline skills."""

from __future__ import annotations

import structlog

from src.skills.base import SkillCallable, SkillResult

logger = structlog.get_logger()


class SkillRegistry:
    """Registry for discovering, registering, and executing skills.

    Usage:
        SkillRegistry.register(my_skill)
        result = await SkillRegistry.execute("my-skill", params)
    """

    _skills: dict[str, SkillCallable] = {}

    @classmethod
    def register(cls, skill: SkillCallable) -> None:
        """Register a skill by its name.

        Args:
            skill: SkillCallable instance. Must have a non-empty name.

        Raises:
            ValueError: If skill name is empty or already registered.
        """
        if not skill.name:
            raise ValueError(f"Skill must have a non-empty name, got {type(skill).__name__}")

        if skill.name in cls._skills:
            logger.warning("skill_registry: overwriting existing skill", name=skill.name)

        cls._skills[skill.name] = skill
        logger.info("skill_registry: registered", name=skill.name)

    @classmethod
    def unregister(cls, name: str) -> None:
        """Remove a registered skill."""
        if name in cls._skills:
            del cls._skills[name]
            logger.info("skill_registry: unregistered", name=name)

    @classmethod
    async def execute(cls, name: str, params: dict) -> SkillResult:
        """Execute a skill by name with safe_execute.

        Args:
            name: Registered skill name.
            params: Skill-specific parameters.

        Returns:
            SkillResult — always returns, never raises.
        """
        skill = cls._skills.get(name)
        if not skill:
            return SkillResult(
                success=False,
                error=f"Skill '{name}' not found. Registered: {list(cls._skills.keys())}",
            )

        logger.info("skill_registry: executing", name=name)
        return await skill.safe_execute(params)

    @classmethod
    def get_skill(cls, name: str) -> SkillCallable | None:
        """Get a registered skill by name."""
        return cls._skills.get(name)

    @classmethod
    def list_skills(cls) -> list[dict]:
        """List all registered skills with metadata."""
        return [
            {
                "name": s.name,
                "description": s.description,
            }
            for s in cls._skills.values()
        ]

    @classmethod
    def clear(cls) -> None:
        """Unregister all skills (useful for testing)."""
        cls._skills.clear()
