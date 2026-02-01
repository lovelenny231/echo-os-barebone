"""
ECHO OS Barebone: JWT Service

JWT token creation and verification.
"""

import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

import jwt

from ..utils.env import env
from ..core.logging import get_logger

logger = get_logger(__name__)


class JWTService:
    """JWT service for session management."""

    def __init__(self):
        self.secret_key = env.JWT_SECRET_KEY or secrets.token_urlsafe(32)
        self.algorithm = env.JWT_ALGORITHM
        self.key_id = env.JWT_KEY_ID
        self.leeway = env.JWT_LEEWAY

        if not env.JWT_SECRET_KEY:
            logger.warning("JWT_SECRET_KEY not set, using random key (not suitable for production)")

    def create_session_token(
        self,
        user_id: str,
        tenant_id: str,
        client_id: Optional[str] = None,
        role: str = "office_staff",
        expires_hours: int = 24,
        extra_claims: Optional[Dict[str, Any]] = None
    ) -> str:
        """Create a JWT session token.

        Args:
            user_id: User identifier
            tenant_id: Tenant identifier
            client_id: Optional client identifier
            role: User role
            expires_hours: Token expiration in hours
            extra_claims: Additional JWT claims

        Returns:
            JWT token string
        """
        now = datetime.now(timezone.utc)
        expires = now + timedelta(hours=expires_hours)

        payload = {
            "sub": user_id,
            "user_id": user_id,
            "tenant_id": tenant_id,
            "role": role,
            "version": 2,  # Token version for future migrations
            "iat": now,
            "exp": expires,
            "kid": self.key_id,
        }

        if client_id:
            payload["client_id"] = client_id

        if extra_claims:
            payload.update(extra_claims)

        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

    def verify_session_token(self, token: str) -> Dict[str, Any]:
        """Verify a JWT session token.

        Args:
            token: JWT token string

        Returns:
            Dict with 'valid' boolean and token claims or 'error' message
        """
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],
                leeway=self.leeway
            )

            return {
                "valid": True,
                "user_id": payload.get("user_id") or payload.get("sub"),
                "tenant_id": payload.get("tenant_id"),
                "client_id": payload.get("client_id"),
                "role": payload.get("role", "office_staff"),
                "version": payload.get("version", 1),
            }

        except jwt.ExpiredSignatureError:
            return {"valid": False, "error": "expired"}
        except jwt.InvalidTokenError as e:
            logger.warning(f"JWT verification failed: {e}")
            return {"valid": False, "error": "invalid"}

    def create_client_token(
        self,
        tenant_id: str,
        client_id: str,
        expires_days: int = 30
    ) -> str:
        """Create a JWT token for client portal access.

        Args:
            tenant_id: Tenant identifier
            client_id: Client identifier
            expires_days: Token expiration in days

        Returns:
            JWT token string
        """
        return self.create_session_token(
            user_id=f"client_{client_id}",
            tenant_id=tenant_id,
            client_id=client_id,
            role="client_user",
            expires_hours=expires_days * 24
        )


# Singleton instance
jwt_service = JWTService()
