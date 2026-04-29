from abc import ABC, abstractmethod
from typing import Any

class PlatformConnector(ABC):
    @abstractmethod
    async def publish(self, content: dict) -> dict:
        """Publish content and return {success, post_id, url, status, error}."""
        pass

    @abstractmethod
    async def get_status(self, post_id: str) -> dict:
        """Get publish status."""
        pass
