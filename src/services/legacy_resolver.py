"""
ECHO OS Barebone: Legacy compatibility layer

Placeholder for legacy tenant_id format conversion.
Customize this for your migration needs.
"""

from typing import Optional, Tuple
from ..utils.env import env
from ..models.tenant import TenantContext

# =============================================================================
# Legacy Mapping Configuration
# =============================================================================
#
# If you have legacy tenant IDs that need to be converted to the new format,
# define them here. Otherwise, leave the mappings empty.
#
# Example:
# OLD_TO_NEW = {
#     "2": ("t_tenant1", "c_client1"),
#     "3": ("t_tenant1", "c_client2"),
# }
#
# =============================================================================

OLD_TO_NEW: dict = {}
NEW_TO_OLD: dict = {}


def is_legacy_format(tenant_id: str) -> bool:
    """Check if tenant_id is in legacy format.

    Args:
        tenant_id: ID to check

    Returns:
        True if legacy format (numeric string or other legacy pattern)
    """
    # New format uses "t_" or "c_" prefix
    if tenant_id.startswith(("t_", "c_")):
        return False
    # Numeric strings are considered legacy
    return tenant_id.isdigit()


def resolve_legacy_tenant(old_tenant_id: str) -> Optional[Tuple[str, str]]:
    """Convert legacy tenant_id to new format.

    Args:
        old_tenant_id: Legacy format tenant_id

    Returns:
        (new_tenant_id, new_client_id) or None if not found
    """
    if not env.LEGACY_COMPAT_ENABLED:
        return None

    return OLD_TO_NEW.get(old_tenant_id)


def get_old_tenant_id(tenant_id: str, client_id: str) -> Optional[str]:
    """Get legacy tenant_id from new format (for dual-write).

    Args:
        tenant_id: New format tenant_id
        client_id: New format client_id

    Returns:
        Legacy tenant_id or None
    """
    if not env.LEGACY_COMPAT_ENABLED:
        return None

    return NEW_TO_OLD.get((tenant_id, client_id))


def resolve_to_context(
    tenant_input: str,
    client_input: Optional[str] = None,
    source: str = "header"
) -> TenantContext:
    """Resolve input to TenantContext.

    Handles both legacy and new formats.

    Args:
        tenant_input: tenant_id or legacy ID
        client_input: client_id (new format only)
        source: Context source ("header", "jwt", "legacy")

    Returns:
        TenantContext
    """
    # Legacy format
    if is_legacy_format(tenant_input):
        mapping = resolve_legacy_tenant(tenant_input)
        if mapping:
            new_tenant_id, new_client_id = mapping
            return TenantContext(
                tenant_id=new_tenant_id,
                client_id=new_client_id,
                source="legacy"
            )
        # No mapping - use as-is
        return TenantContext(
            tenant_id=tenant_input,
            client_id=None,
            source="legacy"
        )

    # New format
    return TenantContext(
        tenant_id=tenant_input,
        client_id=client_input,
        source=source
    )


def normalize_for_query(tenant_id: str, client_id: Optional[str] = None) -> str:
    """Normalize tenant_id for query.

    During migration, converts new format to legacy format if needed.

    Args:
        tenant_id: tenant_id (new or legacy format)
        client_id: client_id (new format)

    Returns:
        Normalized tenant_id
    """
    if is_legacy_format(tenant_id):
        return tenant_id

    if client_id:
        old_id = get_old_tenant_id(tenant_id, client_id)
        if old_id:
            return old_id

    return tenant_id


def normalize_to_tuple(tenant_id: str, client_id: Optional[str] = None) -> Tuple[str, Optional[str]]:
    """Normalize tenant_id/client_id to tuple.

    Converts legacy format to new format.

    Args:
        tenant_id: tenant_id (legacy or new format)
        client_id: client_id (new format only)

    Returns:
        (normalized_tenant_id, normalized_client_id)
    """
    if is_legacy_format(tenant_id):
        mapping = resolve_legacy_tenant(tenant_id)
        if mapping:
            return mapping
        return (tenant_id, None)

    return (tenant_id, client_id)
