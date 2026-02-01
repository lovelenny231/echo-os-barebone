"""ECHO OS Barebone: Tenant models."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from dataclasses import dataclass


class TenantModel(BaseModel):
    """Tenant master data."""

    tenant_id: str = Field(..., description="Tenant ID (e.g., t_xxx)")
    slug: str = Field(..., description="URL-safe identifier")
    name: str = Field(..., description="Tenant name")
    plan: str = Field(default="standard", description="Subscription plan")
    max_clients: int = Field(default=100, description="Maximum clients")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = Field(default=True)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


@dataclass
class TenantContext:
    """API-layer tenant/client context.

    Resolved per request for RAG search and memory storage.
    """

    tenant_id: str
    client_id: Optional[str] = None
    source: str = "header"  # "header", "jwt", "legacy"

    @property
    def has_client(self) -> bool:
        """Check if client_id is set."""
        return self.client_id is not None

    @property
    def memory_pk(self) -> str:
        """Composite PK for conversation memory.

        Returns tenant_id only if no client_id (L3 mode).
        """
        if self.client_id:
            return f"{self.tenant_id}#{self.client_id}"
        return self.tenant_id

    def __repr__(self) -> str:
        return f"TenantContext(tenant={self.tenant_id}, client={self.client_id}, source={self.source})"


class LegacyMapping(BaseModel):
    """Legacy tenant_id to new format mapping."""

    old_tenant_id: str = Field(..., description="Old tenant_id format")
    new_tenant_id: str = Field(..., description="New tenant_id format")
    new_client_id: str = Field(..., description="New client_id format")
