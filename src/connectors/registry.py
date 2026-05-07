from src.connectors.tiktok_connector import TikTokConnector
from src.connectors.shopify_connector import ShopifyConnector
from typing import Any

_CONNECTORS = {
    "tiktok": TikTokConnector,
    "shopify": ShopifyConnector,
}

def get_connector(platform: str):
    connector_cls = _CONNECTORS.get(platform)
    if connector_cls is None:
        raise ValueError(f"Unsupported platform: {platform}")
    return connector_cls()

async def publish_to_platform(platform: str, content: dict[str, Any]) -> dict[str, Any]:
    connector = get_connector(platform)
    return await connector.publish(content)
