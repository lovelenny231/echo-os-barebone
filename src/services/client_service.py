"""
ECHO OS Barebone: Client Service

Service for client management operations.
"""

from typing import Optional, List
from dataclasses import dataclass, field
from datetime import datetime

from ..utils.env import env
from ..core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class Client:
    """Client data class."""
    client_id: str
    tenant_id: str
    slug: str
    name: str
    l4_path: Optional[str] = None  # Path to client-specific data
    is_active: bool = True
    created_at: Optional[datetime] = None
    metadata: dict = field(default_factory=dict)


class ClientService:
    """Service for client operations.

    Note: This is a placeholder implementation.
    In production, implement DynamoDB or database storage.
    """

    def __init__(self):
        self._clients: dict = {}  # key: f"{tenant_id}#{client_slug}"

    def _get_key(self, tenant_id: str, slug: str) -> str:
        """Generate storage key."""
        return f"{tenant_id}#{slug}"

    def get_client_by_slug(self, tenant_id: str, slug: str) -> Optional[Client]:
        """Get client by tenant ID and slug.

        Args:
            tenant_id: Tenant ID
            slug: Client slug

        Returns:
            Client or None if not found
        """
        key = self._get_key(tenant_id, slug)
        return self._clients.get(key)

    def get_client_by_id(self, client_id: str) -> Optional[Client]:
        """Get client by ID.

        Args:
            client_id: Client ID (e.g., "c_xxx")

        Returns:
            Client or None if not found
        """
        for client in self._clients.values():
            if client.client_id == client_id:
                return client
        return None

    def list_clients(self, tenant_id: str) -> List[Client]:
        """List all clients for a tenant.

        Args:
            tenant_id: Tenant ID

        Returns:
            List of clients
        """
        return [
            client for client in self._clients.values()
            if client.tenant_id == tenant_id and client.is_active
        ]

    def create_client(self, client: Client) -> bool:
        """Create a new client.

        Args:
            client: Client to create

        Returns:
            True if successful
        """
        key = self._get_key(client.tenant_id, client.slug)
        self._clients[key] = client
        logger.info(f"Client created: {client.client_id}")
        return True

    def update_client(self, client: Client) -> bool:
        """Update an existing client.

        Args:
            client: Client with updated data

        Returns:
            True if successful
        """
        key = self._get_key(client.tenant_id, client.slug)
        self._clients[key] = client
        logger.info(f"Client updated: {client.client_id}")
        return True

    def delete_client(self, tenant_id: str, client_id: str) -> bool:
        """Soft delete a client.

        Args:
            tenant_id: Tenant ID
            client_id: Client ID to delete

        Returns:
            True if successful
        """
        for key, client in self._clients.items():
            if client.client_id == client_id and client.tenant_id == tenant_id:
                client.is_active = False
                logger.info(f"Client deleted: {client_id}")
                return True
        return False


# Singleton instance
client_service = ClientService()


def get_client_by_slug(tenant_id: str, slug: str) -> Optional[Client]:
    """Convenience function to get client by slug."""
    return client_service.get_client_by_slug(tenant_id, slug)
