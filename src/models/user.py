"""
ECHO OS Barebone: User Model for OAuth Authentication

Represents authenticated users with role-based access.
"""

from datetime import datetime, timezone
from typing import Optional, List
from dataclasses import dataclass, field
from enum import Enum


class UserRole(Enum):
    """User Roles for RBAC"""
    OFFICE_ADMIN = "office_admin"
    OFFICE_STAFF = "office_staff"
    CLIENT_ADMIN = "client_admin"
    CLIENT_USER = "client_user"


class AuthProvider(Enum):
    """Authentication Provider"""
    GOOGLE = "google"
    MICROSOFT = "microsoft"
    PASSWORD = "password"


@dataclass
class User:
    """User Model

    Represents an authenticated user in the system.
    Supports OAuth-based authentication from multiple providers.
    """

    # Primary identifiers
    user_id: str
    tenant_id: str

    # OAuth provider info
    provider: AuthProvider
    provider_sub: str
    email: str

    # Profile
    name: Optional[str] = None
    given_name: Optional[str] = None
    family_name: Optional[str] = None
    picture_url: Optional[str] = None

    # Domain info
    hosted_domain: Optional[str] = None

    # Authorization
    role: UserRole = UserRole.OFFICE_STAFF
    assigned_client_ids: List[str] = field(default_factory=list)

    # Timestamps
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_login_at: Optional[datetime] = None

    # Status
    is_active: bool = True

    def has_access_to_client(self, client_id: str) -> bool:
        """Check if user has access to a specific client.

        OFFICE_ADMIN has access to all clients.
        OFFICE_STAFF only has access to assigned clients.
        """
        if self.role == UserRole.OFFICE_ADMIN:
            return True
        return client_id in self.assigned_client_ids

    def can_manage_users(self) -> bool:
        """Check if user can manage other users"""
        return self.role == UserRole.OFFICE_ADMIN

    def can_create_clients(self) -> bool:
        """Check if user can create new clients"""
        return self.role == UserRole.OFFICE_ADMIN

    def to_dict(self) -> dict:
        """Convert to dictionary for storage"""
        return {
            "user_id": self.user_id,
            "tenant_id": self.tenant_id,
            "provider": self.provider.value,
            "provider_sub": self.provider_sub,
            "email": self.email,
            "name": self.name,
            "given_name": self.given_name,
            "family_name": self.family_name,
            "picture_url": self.picture_url,
            "hosted_domain": self.hosted_domain,
            "role": self.role.value,
            "assigned_client_ids": self.assigned_client_ids,
            "created_at": self.created_at.isoformat(),
            "last_login_at": self.last_login_at.isoformat() if self.last_login_at else None,
            "is_active": self.is_active,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'User':
        """Create from dictionary"""
        if isinstance(data.get("created_at"), str):
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        if isinstance(data.get("last_login_at"), str) and data["last_login_at"]:
            data["last_login_at"] = datetime.fromisoformat(data["last_login_at"])

        if isinstance(data.get("provider"), str):
            data["provider"] = AuthProvider(data["provider"])
        if isinstance(data.get("role"), str):
            data["role"] = UserRole(data["role"])

        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class UserSession:
    """User Session

    Represents an active authentication session.
    """
    session_id: str
    user_id: str
    tenant_id: str

    # OAuth tokens
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    token_expires_at: Optional[datetime] = None

    # Session metadata
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_activity_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Client info
    user_agent: Optional[str] = None
    ip_address: Optional[str] = None

    def is_expired(self) -> bool:
        """Check if session is expired"""
        return datetime.now(timezone.utc) > self.expires_at

    def is_token_expired(self) -> bool:
        """Check if OAuth token is expired"""
        if not self.token_expires_at:
            return True
        return datetime.now(timezone.utc) > self.token_expires_at
