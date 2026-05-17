from __future__ import annotations

import pytest


@pytest.fixture
def skill():
    from src.skills.product_strategy import ProductStrategySkill
    return ProductStrategySkill()


class TestValidateParams:

    def test_missing_product_catalog(self, skill):
        errors = skill.validate_params({})
        assert any("missing 'product_catalog'" in e for e in errors)

    def test_root_name_passes(self, skill):
        errors = skill.validate_params({"product_catalog": {"name": "red apple"}})
        assert not any("missing product_name" in e for e in errors)

    def test_root_product_name_passes(self, skill):
        errors = skill.validate_params({"product_catalog": {"product_name": "red apple"}})
        assert not any("missing product_name" in e for e in errors)

    def test_nested_products_name_passes(self, skill):
        errors = skill.validate_params({
            "product_catalog": {
                "products": [{"name": "red apple", "usps": []}]
            }
        })
        assert not any("missing product_name" in e for e in errors)

    def test_nested_products_product_name_passes(self, skill):
        errors = skill.validate_params({
            "product_catalog": {
                "products": [{"product_name": "red apple"}]
            }
        })
        assert not any("missing product_name" in e for e in errors)

    def test_empty_products_array_fails(self, skill):
        errors = skill.validate_params({"product_catalog": {"products": []}})
        assert any("missing product_name" in e for e in errors)

    def test_products_without_name_fails(self, skill):
        errors = skill.validate_params({
            "product_catalog": {"products": [{"category": "food"}]}
        })
        assert any("missing product_name" in e for e in errors)

    def test_completely_empty_catalog_fails(self, skill):
        errors = skill.validate_params({"product_catalog": {}})
        assert any("missing product_name" in e for e in errors)
