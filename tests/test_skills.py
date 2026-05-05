"""Tests for Skill engine and ProductCatalog.

Verifies:
1. SkillCallable ABC: can be subclassed, safe_execute cycle (async)
2. SkillRegistry: register/unregister/execute/list (async execute)
3. LLMSkill: prompt injection, param validation, fallback
4. ProductCatalog: CRUD, search, mock mode, dict conversion
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.skills.base import SkillCallable, SkillResult
from src.skills.registry import SkillRegistry
from src.skills.llm_skill import LLMSkill
from src.tools.product_catalog import Product, ProductCatalog


# ==============================================================================
# Fixtures
# ==============================================================================


class EchoSkill(SkillCallable):
    """Test skill that echoes back params."""

    name = "echo"
    description = "Echoes input params for testing"

    async def execute(self, params: dict) -> SkillResult:
        return SkillResult(success=True, data=params)

    def validate_params(self, params: dict) -> list[str]:
        if "required_field" not in params:
            return ["missing required_field"]
        return []

    def validate_output(self, data) -> list[str]:
        if not isinstance(data, dict):
            return ["output must be dict"]
        return []

    def fallback(self, params: dict) -> SkillResult:
        return SkillResult(success=True, data={"fallback": True})


class FailingSkill(SkillCallable):
    """Test skill that always fails."""

    name = "failing"
    description = "Always fails for testing fallback"

    max_retries = 1

    async def execute(self, params: dict) -> SkillResult:
        raise RuntimeError("Intentional failure")

    def validate_params(self, params: dict) -> list[str]:
        return []

    def validate_output(self, data) -> list[str]:
        return []

    def fallback(self, params: dict) -> SkillResult:
        return SkillResult(success=True, data={"note": "fallback activated"})


# ==============================================================================
# SkillResult Tests
# ==============================================================================


class TestSkillResult:
    """SkillResult data envelope."""

    def test_success_result(self):
        result = SkillResult(success=True, data={"key": "value"})
        assert result.success is True
        assert result.data == {"key": "value"}
        assert result.error is None

    def test_failure_result(self):
        result = SkillResult(success=False, error="something went wrong")
        assert result.success is False
        assert result.error == "something went wrong"

    def test_metadata_defaults(self):
        result = SkillResult(success=True, data=42)
        assert result.metadata == {}

    def test_metadata_custom(self):
        result = SkillResult(success=True, data={}, metadata={"latency": 1.5})
        assert result.metadata["latency"] == 1.5

    def test_repr(self):
        result = SkillResult(success=True, data={"a": 1})
        assert "SkillResult" in repr(result)


# ==============================================================================
# SkillCallable Tests
# ==============================================================================


class TestSkillCallable:
    """Abstract base behavior."""

    @pytest.fixture
    def echo(self):
        return EchoSkill()

    def test_execute_returns_result(self, echo):
        """execute should return SkillResult."""
        import asyncio

        result = asyncio.run(echo.execute(params={"required_field": "hello"}))
        assert result.success is True
        assert result.data["required_field"] == "hello"

    def test_safe_execute_validates_params(self, echo):
        """safe_execute should fail on invalid params."""
        import asyncio

        result = asyncio.run(echo.safe_execute(params={}))
        assert result.success is False
        assert "missing required_field" in result.error

    def test_safe_execute_validates_output(self, echo):
        """safe_execute should validate output."""
        import asyncio

        result = asyncio.run(echo.safe_execute(params={"required_field": "ok"}))
        assert result.success is True
        assert result.data["required_field"] == "ok"

    def test_fallback_on_all_retries(self):
        """safe_execute should return fallback when all retries fail."""
        import asyncio

        skill = FailingSkill()
        result = asyncio.run(skill.safe_execute(params={}))
        assert result.success is True
        assert result.data["note"] == "fallback activated"

    def test_fallback_has_metadata(self):
        """Fallback result should include retry metadata."""
        import asyncio

        skill = FailingSkill()
        result = asyncio.run(skill.safe_execute(params={}))
        assert "retries" in result.metadata
        assert "fallback_reason" in result.metadata


# ==============================================================================
# SkillRegistry Tests
# ==============================================================================


class TestSkillRegistry:
    """Registry operations."""

    def setup_method(self):
        SkillRegistry.clear()

    def test_register_skill(self):
        """Should register a skill by name."""
        skill = EchoSkill()
        SkillRegistry.register(skill)
        assert SkillRegistry.get_skill("echo") is skill

    def test_register_duplicate_overwrites(self):
        """Registering same name should overwrite."""
        SkillRegistry.register(EchoSkill())
        assert SkillRegistry.get_skill("echo") is not None
        skill2 = EchoSkill()
        SkillRegistry.register(skill2)
        assert SkillRegistry.get_skill("echo") is skill2

    def test_unregister_skill(self):
        """Should unregister a skill."""
        SkillRegistry.register(EchoSkill())
        assert len(SkillRegistry._skills) == 1
        SkillRegistry.unregister("echo")
        assert "echo" not in SkillRegistry._skills

    def test_execute_registered_skill(self):
        """Should execute a registered skill."""
        import asyncio

        SkillRegistry.register(EchoSkill())
        result = asyncio.run(SkillRegistry.execute("echo", {"required_field": "test"}))
        assert result.success is True

    def test_execute_unregistered_skill(self):
        """Should fail gracefully for unregistered skill."""
        import asyncio

        result = asyncio.run(SkillRegistry.execute("nonexistent", {}))
        assert result.success is False
        assert "not found" in result.error

    def test_list_skills(self):
        """Should list all registered skills."""
        SkillRegistry.register(EchoSkill())
        skills = SkillRegistry.list_skills()
        assert len(skills) == 1
        assert skills[0]["name"] == "echo"

    def test_clear_skills(self):
        """Should clear all skills."""
        SkillRegistry.register(EchoSkill())
        assert len(SkillRegistry._skills) == 1
        SkillRegistry.clear()
        assert len(SkillRegistry._skills) == 0


# ==============================================================================
# LLMSkill Tests
# ==============================================================================


class TestLLMSkillInit:
    """LLMSkill initialization."""

    def test_minimal_init(self):
        """Should init with minimal params."""
        skill = LLMSkill(
            name="test-skill",
            description="A test skill",
            system_prompt="You are a helper.",
            user_message_template="Do something with {input}",
        )
        assert skill.name == "test-skill"
        assert skill.max_retries == 3

    def test_init_with_fallback(self):
        """Should accept fallback data."""
        skill = LLMSkill(
            name="safe-skill",
            description="With fallback",
            system_prompt="Do X",
            user_message_template="Use {data}",
            fallback_data={"result": "fallback_result"},
        )
        assert skill._fallback_data == {"result": "fallback_result"}


class TestLLMSkillPromptInjection:
    """Parameter injection into prompt templates."""

    @pytest.fixture
    def skill(self):
        return LLMSkill(
            name="inject-test",
            description="Test injection",
            system_prompt="You are a {role}.",
            user_message_template="Create content for {product}: {usps}",
        )

    def test_inject_simple_param(self, skill):
        """Should replace {param} with simple values."""
        result = skill._inject_params("Hello {name}", {"name": "World"})
        assert result == "Hello World"

    def test_inject_multiple_params(self, skill):
        """Should replace multiple params."""
        result = skill._inject_params(
            "{a} and {b}",
            {"a": "1", "b": "2"},
        )
        assert result == "1 and 2"

    def test_inject_missing_param_leaves_placeholder(self, skill):
        """Missing params should leave placeholder unchanged."""
        result = skill._inject_params("{present} and {missing}", {"present": "here"})
        assert "{missing}" in result

    def test_inject_json_params(self, skill):
        """Dict/list params should be JSON-serialized."""
        result = skill._inject_params("data: {items}", {"items": [1, 2, 3]})
        assert "[1, 2, 3]" in result

    def test_system_and_user_injected(self, skill):
        """Both system prompt and user message should get injection."""
        system = skill._inject_params(skill._system_prompt, {"role": "assistant"})
        user = skill._inject_params(
            skill._user_message_template,
            {"product": "X1", "usps": "quiet, portable"},
        )
        assert "assistant" in system
        assert "X1" in user
        assert "quiet, portable" in user


class TestLLMSkillFallback:
    """Fallback behavior."""

    def test_fallback_returns_provided_data(self):
        """Fallback should return the fallback_data."""
        skill = LLMSkill(
            name="fb-test",
            description="Test",
            system_prompt="",
            user_message_template="",
            fallback_data={"default": "value"},
        )
        result = skill.fallback({})
        assert result.success is True
        assert result.data["default"] == "value"

    def test_fallback_without_data_returns_note(self):
        """Without fallback_data, should return a note."""
        skill = LLMSkill(
            name="no-fb",
            description="No fallback",
            system_prompt="",
            user_message_template="",
        )
        result = skill.fallback({})
        assert result.success is True
        assert "[no-fb fallback]" in result.data["note"]


# ==============================================================================
# ProductCatalog Tests
# ==============================================================================


class TestProduct:
    """Product data model."""

    def test_product_init(self):
        """Should create product with all fields."""
        p = Product(
            product_id="P001",
            name="Test Product",
            brand="TestBrand",
            description="A test",
            usps=["feature 1", "feature 2"],
            image_url="https://img.com/p.jpg",
            price=99.99,
            category="testing",
        )
        assert p.name == "Test Product"
        assert len(p.usps) == 2

    def test_product_to_dict(self):
        """Should convert to dict."""
        p = Product(product_id="P1", name="X", brand="B")
        d = p.to_dict()
        assert d["product_id"] == "P1"
        assert d["name"] == "X"

    def test_product_from_dict(self):
        """Should create from dict."""
        p = Product.from_dict({
            "product_id": "P2",
            "name": "Y",
            "brand": "C",
            "usps": ["a"],
        })
        assert p.product_id == "P2"
        assert p.usps == ["a"]

    def test_product_default_usps(self):
        """USPs should default to empty list."""
        p = Product(product_id="P3", name="Z", brand="D")
        assert p.usps == []


class TestProductCatalogMock:
    """Mock mode seeding."""

    @pytest.fixture
    def catalog(self):
        return ProductCatalog(use_mock=True)

    def test_mock_has_products(self, catalog):
        """Mock catalog should have seed data."""
        products = catalog.get_all()
        assert len(products) == 3

    def test_mock_has_pump(self, catalog):
        """Mock catalog should contain the wearable pump."""
        pump = catalog.get("PROD-MOCK-001")
        assert pump is not None
        assert "wearable" in pump.name.lower()

    def test_mock_search(self, catalog):
        """Should search across name/brand/description."""
        results = catalog.search("pump")
        assert len(results) >= 1
        assert any("pump" in p.name.lower() for p in results)

    def test_mock_to_dict(self, catalog):
        """to_dict should return compatible format."""
        d = catalog.to_dict()
        assert "products" in d
        assert d["total_count"] == 3


class TestProductCatalogCRUD:
    """CRUD operations."""

    @pytest.fixture
    def catalog(self):
        return ProductCatalog(use_mock=False)

    def test_add_product(self, catalog):
        """Should add a product."""
        p = Product(product_id="NEW-1", name="New", brand="Brand")
        added = catalog.add(p)
        assert added.product_id == "NEW-1"
        assert catalog.get("NEW-1") is not None

    def test_add_auto_generates_id(self, catalog):
        """Should generate ID if not provided (空字符串触发自动 PROD- 前缀生成)。"""
        p = Product(product_id="", name="No ID", brand="B")
        added = catalog.add(p)
        assert added.product_id.startswith("PROD-")

    def test_get_nonexistent(self, catalog):
        """Getting missing ID returns None."""
        assert catalog.get("FAKE-ID") is None

    def test_update_product(self, catalog):
        """Should update product fields."""
        p = Product(product_id="UPD-1", name="Old", brand="B")
        catalog.add(p)
        updated = catalog.update("UPD-1", name="New Name", price=49.99)
        assert updated is not None
        assert updated.name == "New Name"
        assert updated.price == 49.99

    def test_update_nonexistent(self, catalog):
        """Updating missing ID returns None."""
        assert catalog.update("FAKE", name="X") is None

    def test_delete_product(self, catalog):
        """Should delete a product."""
        p = Product(product_id="DEL-1", name="Delete Me", brand="B")
        catalog.add(p)
        assert catalog.delete("DEL-1") is True
        assert catalog.get("DEL-1") is None

    def test_delete_nonexistent(self, catalog):
        """Deleting missing ID returns False."""
        assert catalog.delete("FAKE") is False

    def test_file_persistence(self, tmp_path):
        """Should persist to JSON file."""
        db_path = tmp_path / "products.json"
        cat1 = ProductCatalog(storage_path=db_path)
        cat1.add(Product(product_id="PERSIST-1", name="Persist Me", brand="P"))
        del cat1

        cat2 = ProductCatalog(storage_path=db_path)
        assert cat2.get("PERSIST-1") is not None
        assert cat2.get("PERSIST-1").name == "Persist Me"

    def test_empty_catalog(self, catalog):
        """New catalog should be empty."""
        assert len(catalog.get_all()) == 0
