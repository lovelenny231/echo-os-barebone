"""
ECHO OS Barebone: FastAPI Dependency Injection

TenantContext resolution and authentication dependencies.
"""

from typing import Optional
from datetime import datetime, timezone
from fastapi import Request, Header, HTTPException, Depends, Cookie

from ..models.tenant import TenantContext
from ..models.user import User, UserRole, AuthProvider, UserSession
from ..services.legacy_resolver import resolve_to_context, is_legacy_format
from ..services.jwt_service import jwt_service
from ..utils.env import env
from ..core.logging import get_logger

logger = get_logger(__name__)


async def get_tenant_context(
    request: Request,
    x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-ID"),
    x_client_id: Optional[str] = Header(None, alias="X-Client-ID"),
) -> TenantContext:
    """Resolve TenantContext from request.

    Priority:
    1. X-Tenant-ID / X-Client-ID headers
    2. Request body tenant_id

    Args:
        request: FastAPI Request
        x_tenant_id: X-Tenant-ID header
        x_client_id: X-Client-ID header

    Returns:
        TenantContext
    """
    tenant_id = x_tenant_id
    client_id = x_client_id

    # Fallback to body for backward compatibility
    if not tenant_id:
        try:
            if hasattr(request.state, "json_body"):
                body = request.state.json_body
            else:
                body = await request.json()
                request.state.json_body = body

            tenant_id = body.get("tenant_id", "1")
            if not client_id:
                client_id = body.get("client_id")
        except Exception:
            tenant_id = "1"

    ctx = resolve_to_context(tenant_id, client_id, source="header")

    from ..core.logging import set_context
    set_context(
        tenant_id=ctx.tenant_id,
        client_id=ctx.client_id,
        request_id=getattr(request.state, "correlation_id", None)
    )

    return ctx


async def get_tenant_context_from_jwt(
    request: Request,
    client_session: Optional[str] = Cookie(None, alias="client_session"),
) -> TenantContext:
    """Resolve TenantContext from JWT (for client portal).

    Args:
        request: FastAPI Request
        client_session: Session JWT cookie

    Returns:
        TenantContext

    Raises:
        HTTPException: Invalid JWT
    """
    # Auth bypass mode (testing)
    if env.CLIENT_AUTH_BYPASS:
        return TenantContext(
            tenant_id="t_default",
            client_id="c_default",
            source="bypass"
        )

    if not client_session:
        raise HTTPException(status_code=401, detail="Not authenticated")

    result = jwt_service.verify_session_token(client_session)

    if not result.get("valid"):
        error = result.get("error", "invalid")
        if error == "expired":
            raise HTTPException(status_code=401, detail="Session expired")
        raise HTTPException(status_code=401, detail="Invalid session")

    tenant_id = result.get("tenant_id")
    client_id = result.get("client_id")
    version = result.get("version", 1)

    if version == 1 and is_legacy_format(tenant_id):
        ctx = resolve_to_context(tenant_id, None, source="jwt")
    else:
        ctx = TenantContext(
            tenant_id=tenant_id,
            client_id=client_id,
            source="jwt"
        )

    from ..core.logging import set_context
    set_context(
        tenant_id=ctx.tenant_id,
        client_id=ctx.client_id,
        request_id=getattr(request.state, "correlation_id", None)
    )

    return ctx


TenantContextDep = TenantContext


# =============================================================================
# OAuth/Session Authentication Dependencies
# =============================================================================

AUTH_SESSION_COOKIE_NAME = "auth_session"


async def get_current_user(
    request: Request,
    auth_session: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
) -> Optional[User]:
    """Get current authenticated user.

    Authentication priority:
    1. OAuth session cookie (auth_session)
    2. Bearer JWT (Authorization header)
    3. None (unauthenticated)

    Args:
        request: FastAPI Request
        auth_session: OAuth session cookie
        authorization: Authorization header (Bearer token)

    Returns:
        User if authenticated, None otherwise
    """
    # 1. OAuth session cookie
    if auth_session:
        user = await _get_user_from_oauth_session(auth_session)
        if user:
            return user

    # 2. Bearer JWT
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
        user = await _get_user_from_jwt(token)
        if user:
            return user

    return None


async def require_office_auth(
    user: Optional[User] = Depends(get_current_user),
) -> User:
    """Require office authentication.

    OFFICE_ADMIN or OFFICE_STAFF role required.

    Args:
        user: User from get_current_user

    Returns:
        User

    Raises:
        HTTPException 401: Not authenticated
        HTTPException 403: Insufficient permissions
    """
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if user.role not in (UserRole.OFFICE_ADMIN, UserRole.OFFICE_STAFF):
        logger.warning(
            "access_denied_role",
            extra={"user_id": user.user_id, "role": user.role.value}
        )
        raise HTTPException(
            status_code=403,
            detail="Office admin or staff role required",
        )

    return user


async def require_office_admin(
    user: User = Depends(require_office_auth),
) -> User:
    """Require office admin role.

    Args:
        user: User from require_office_auth

    Returns:
        User

    Raises:
        HTTPException 403: Admin role required
    """
    if user.role != UserRole.OFFICE_ADMIN:
        raise HTTPException(
            status_code=403,
            detail="Office admin role required",
        )
    return user


# =============================================================================
# Internal Helper Functions
# =============================================================================

async def _get_user_from_oauth_session(session_id: str) -> Optional[User]:
    """Get user from OAuth session.

    Note: Implement with your auth_api session store or database.
    """
    try:
        from .auth_api import _get_user_session

        session = _get_user_session(session_id)
        if not session:
            return None

        user = User(
            user_id=session.user_id,
            tenant_id=session.tenant_id,
            provider=AuthProvider.GOOGLE,
            provider_sub=session.user_id.replace("u_", ""),
            email="",
            role=UserRole.OFFICE_STAFF,
        )

        logger.info(
            "oauth_session_auth_success",
            extra={"user_id": user.user_id, "tenant_id": user.tenant_id}
        )

        return user

    except ImportError:
        logger.warning("auth_api_not_available")
        return None
    except Exception as e:
        logger.error("oauth_session_auth_error", extra={"error": str(e)})
        return None


async def _get_user_from_jwt(token: str) -> Optional[User]:
    """Get user from JWT token."""
    try:
        result = jwt_service.verify_session_token(token)

        if not result.get("valid"):
            return None

        user_id = result.get("user_id")
        tenant_id = result.get("tenant_id")
        role_str = result.get("role", "office_staff")

        if not user_id or not tenant_id:
            return None

        try:
            role = UserRole(role_str)
        except ValueError:
            role = UserRole.OFFICE_STAFF

        user = User(
            user_id=user_id,
            tenant_id=tenant_id,
            provider=AuthProvider.PASSWORD,
            provider_sub=user_id,
            email="",
            role=role,
        )

        logger.info(
            "jwt_auth_success",
            extra={"user_id": user.user_id, "tenant_id": user.tenant_id}
        )

        return user

    except Exception as e:
        logger.error("jwt_auth_error", extra={"error": str(e)})
        return None


def get_user_for_client_access(
    user: Optional[User],
    client_id: str,
) -> bool:
    """Check if user can access specific client.

    Args:
        user: Authenticated user (may be None)
        client_id: Target client_id

    Returns:
        True if access allowed
    """
    if not user:
        return False

    return user.has_access_to_client(client_id)
