"""Product catalog management.

Simple in-memory + JSON-backed product catalog.
Stores product info needed by the pipeline: name, USPs, brand, image URL, price.

Supports mock mode for development without a database.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger()


class Product:
    """A product item in the catalog."""

    def __init__(
        self,
        product_id: str,
        name: str,
        brand: str,
        description: str = "",
        usps: list[str] | None = None,
        image_url: str = "",
        price: float = 0.0,
        category: str = "",
        metadata: dict[str, Any] | None = None,
    ):
        self.product_id = product_id
        self.name = name
        self.brand = brand
        self.description = description
        self.usps = usps or []
        self.image_url = image_url
        self.price = price
        self.category = category
        self.metadata = metadata or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "product_id": self.product_id,
            "name": self.name,
            "brand": self.brand,
            "description": self.description,
            "usps": self.usps,
            "image_url": self.image_url,
            "price": self.price,
            "category": self.category,
            **self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Product:
        return cls(
            product_id=data.get("product_id", ""),
            name=data.get("name", ""),
            brand=data.get("brand", ""),
            description=data.get("description", ""),
            usps=data.get("usps", []),
            image_url=data.get("image_url", ""),
            price=data.get("price", 0.0),
            category=data.get("category", ""),
        )


class ProductCatalog:
    """Product catalog with CRUD operations.

    Two modes:
    1. Real: in-memory with JSON file persistence
    2. Mock: pre-populated with sample products for testing
    """

    def __init__(
        self,
        storage_path: Path | None = None,
        use_mock: bool = False,
    ):
        self.storage_path = storage_path
        self._products: dict[str, Product] = {}
        self.use_mock = use_mock

        if use_mock:
            self._seed_mock_data()
        elif storage_path and storage_path.exists():
            self._load()

    # ── Public API ──

    def add(self, product: Product) -> Product:
        """Add or update a product."""
        if not product.product_id:
            product.product_id = f"PROD-{uuid.uuid4().hex[:8].upper()}"
        self._products[product.product_id] = product
        self._save()
        return product

    def get(self, product_id: str) -> Product | None:
        """Get a product by ID."""
        return self._products.get(product_id)

    def get_all(self) -> list[Product]:
        """Get all products."""
        return list(self._products.values())

    def update(self, product_id: str, **updates) -> Product | None:
        """Update product fields in-place."""
        product = self._products.get(product_id)
        if not product:
            return None
        for key, value in updates.items():
            if hasattr(product, key):
                setattr(product, key, value)
        self._save()
        return product

    def delete(self, product_id: str) -> bool:
        """Delete a product by ID."""
        if product_id in self._products:
            del self._products[product_id]
            self._save()
            return True
        return False

    def search(self, query: str) -> list[Product]:
        """Simple text search across name, brand, description."""
        query_lower = query.lower()
        results = []
        for product in self._products.values():
            if (
                query_lower in product.name.lower()
                or query_lower in product.brand.lower()
                or query_lower in product.description.lower()
            ):
                results.append(product)
        return results

    def to_dict(self) -> dict[str, Any]:
        """Convert catalog to dict (compatible with existing product_catalog param)."""
        products = [p.to_dict() for p in self._products.values()]
        return {
            "products": products,
            "total_count": len(products),
        }

    # ── Internal ──

    def _load(self):
        try:
            data = json.loads(self.storage_path.read_text())
            for item in data:
                product = Product.from_dict(item)
                self._products[product.product_id] = product
        except (json.JSONDecodeError, OSError):
            self._products = {}

    def _save(self):
        if self.storage_path:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            data = [p.to_dict() for p in self._products.values()]
            self.storage_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    def _seed_mock_data(self):
        self._products = {
            "PROD-MOCK-001": Product(
                product_id="PROD-MOCK-001",
                name="Wearable Breast Pump X1",
                brand="LactFit",
                description="A silent, hands-free wearable breast pump for working mothers.",
                usps=["ultra-silent motor", "hands-free wear", "2-hour battery", "easy clean"],
                image_url="https://example.com/pump_x1.jpg",
                price=299.99,
                category="breast_pumps",
            ),
            "PROD-MOCK-002": Product(
                product_id="PROD-MOCK-002",
                name="Baby Bottle Warmer Pro",
                brand="LactFit",
                description="Smart temperature-controlled bottle warmer with app connectivity.",
                usps=["precise temp control", "app-connected", "fast warm (3 min)", "auto shut-off"],
                image_url="https://example.com/warmer_pro.jpg",
                price=79.99,
                category="feeding",
            ),
            "PROD-MOCK-003": Product(
                product_id="PROD-MOCK-003",
                name="Nursing Pillow Deluxe",
                brand="LactFit",
                description="Ergonomic nursing pillow with multiple positioning options.",
                usps=["ergonomic design", "machine washable", "multi-position", "infant to toddler"],
                image_url="https://example.com/pillow_dlx.jpg",
                price=49.99,
                category="nursing",
            ),
        }
