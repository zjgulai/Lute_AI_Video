"""SkillRegistry — central registry for all pipeline skills."""

from __future__ import annotations

from typing import Any

import structlog

from src.skills.base import SkillCallable, SkillResult

logger = structlog.get_logger()


class SkillRegistry:
    """Registry for discovering, registering, and executing skills.

    Usage:
        SkillRegistry.register(my_skill)
        reg = SkillRegistry()
        result = await reg.execute("my-skill", params)

    P2-7: _skills moved from class variable to instance variable so each
    registry instance has its own isolated skill set. Class-level _global_skills
    remains for import-time registration (``SkillRegistry.register``).
    """

    _global_skills: dict[str, SkillCallable] = {}

    def __init__(self) -> None:
        # Instance-local copy of the global skill set at creation time.
        # Tests can mutate this without affecting other instances.
        self._skills: dict[str, SkillCallable] = dict(self.__class__._global_skills)

    @classmethod
    def register(cls, skill: SkillCallable) -> None:
        """Register a skill globally (import-time side-effect).

        Args:
            skill: SkillCallable instance. Must have a non-empty name.

        Raises:
            ValueError: If skill name is empty or already registered.
        """
        if not skill.name:
            raise ValueError(f"Skill must have a non-empty name, got {type(skill).__name__}")

        if skill.name in cls._global_skills:
            logger.warning("skill_registry: overwriting existing skill", name=skill.name)

        cls._global_skills[skill.name] = skill
        logger.info("skill_registry: registered", name=skill.name)

    @classmethod
    def unregister(cls, name: str) -> None:
        """Remove a skill from the global registry."""
        if name in cls._global_skills:
            del cls._global_skills[name]
            logger.info("skill_registry: unregistered", name=name)

    async def execute(self, name: str, params: dict[str, Any]) -> SkillResult:
        """Execute a skill by name with safe_execute.

        Args:
            name: Registered skill name.
            params: Skill-specific parameters.

        Returns:
            SkillResult — always returns, never raises.
        """
        skill = self._skills.get(name)
        if not skill:
            return SkillResult(
                success=False,
                error=f"Skill '{name}' not found. Registered: {list(self._skills.keys())}",
            )

        logger.info("skill_registry: executing", name=name)
        return await skill.safe_execute(params)

    def get_skill(self, name: str) -> SkillCallable | None:
        """Get a registered skill by name."""
        return self._skills.get(name)

    def list_skills(self) -> list[dict[str, Any]]:
        """List all registered skills with metadata."""
        return [
            {
                "name": s.name,
                "description": s.description,
            }
            for s in self._skills.values()
        ]

    def clear(self) -> None:
        """Unregister all skills on this instance (useful for testing)."""
        self._skills.clear()

    @classmethod
    def clear_global(cls) -> None:
        """Unregister all skills from the global registry."""
        cls._global_skills.clear()
