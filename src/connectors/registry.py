from dataclasses import dataclass
from typing import Any, Literal

from src.connectors.base import ConnectorCredentialReason
from src.connectors.shopify_connector import ShopifyConnector
from src.connectors.tiktok_connector import TikTokConnector


@dataclass(frozen=True, slots=True)
class PublishConnectorReadiness:
    platform: Literal["tiktok", "shopify"]
    ready: bool
    reason: ConnectorCredentialReason | None


_CONNECTORS = {
    "tiktok": TikTokConnector,
    "shopify": ShopifyConnector,
}


def get_connector(platform: str):
    connector_cls = _CONNECTORS.get(platform)
    if connector_cls is None:
        raise ValueError(f"Unsupported platform: {platform}")
    return connector_cls()


def inspect_publish_readiness(platform: str) -> PublishConnectorReadiness:
    """Project strict credential readiness without network or connector creation."""

    if platform == "tiktok":
        from src.connectors.tiktok_connector import _credential_state

        selected_platform: Literal["tiktok", "shopify"] = "tiktok"
    elif platform == "shopify":
        from src.connectors.shopify_connector import _credential_state

        selected_platform = "shopify"
    else:
        raise ValueError(f"Unsupported platform: {platform}")
    state = _credential_state()
    return PublishConnectorReadiness(
        platform=selected_platform,
        ready=state.ready,
        reason=state.reason,
    )


async def publish_to_platform(platform: str, content: dict[str, Any]) -> dict[str, Any]:
    connector = get_connector(platform)
    preflight = await connector.preflight(content)
    return await connector.publish(content, preflight=preflight)
