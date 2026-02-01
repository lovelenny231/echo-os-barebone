"""
ECHO OS Barebone: Query Handler

Main query processing with RAG integration.
"""

import os
import json
from datetime import datetime
from typing import Dict, Any, List, Optional

from ..core.logging import get_logger, add_route_trace, add_layer_accessed
from ..utils.env import env
from .llm import llm_factory, LLMMessage, LLMConfig
from .llm.prompts import build_system_prompt

logger = get_logger(__name__)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Main query handler.

    Processes chat requests and returns AI-generated responses.
    Compatible with Lambda event format and direct FastAPI calls.

    Args:
        event: Request event (Lambda format)
        context: Lambda context (unused)

    Returns:
        Response dict with statusCode and body
    """
    add_route_trace("query_handler")

    try:
        # Parse request
        if isinstance(event.get("body"), str):
            body = json.loads(event["body"])
        else:
            body = event.get("body", {})

        message = body.get("message", "")
        user_id = body.get("user_id", "anonymous")
        session_id = body.get("session_id", "default")
        tenant_id = body.get("tenant_id", "1")
        client_id = body.get("client_id")
        conversation_history = body.get("conversation_history", [])

        logger.info(
            "query_received",
            extra={
                "tenant_id": tenant_id,
                "client_id": client_id,
                "message_len": len(message),
            }
        )

        if not message:
            return _error_response(400, "Message is required")

        # Build context from each layer
        l1_context = _get_l1_context(message) if env.L1_ENABLED else ""
        l3_context = _get_l3_context(message, tenant_id) if env.L3_ENABLED else ""
        l4_context = _get_l4_context(message, tenant_id, client_id) if env.L4_ENABLED else ""
        l5_context = _get_l5_context(tenant_id, client_id, session_id) if env.L5_ENABLED else ""

        # Get company name (placeholder)
        company_name = _get_company_name(client_id)

        # Build system prompt
        system_prompt = build_system_prompt(
            l1_context=l1_context,
            l3_context=l3_context,
            l4_context=l4_context,
            l5_context=l5_context,
            company_name=company_name,
            cbr_context=""
        )

        # Build messages
        messages = [LLMMessage(role="system", content=system_prompt)]

        # Add conversation history
        for hist in conversation_history[-5:]:  # Last 5 turns
            if hist.get("role") in ("user", "assistant"):
                messages.append(LLMMessage(
                    role=hist["role"],
                    content=hist.get("content", "")
                ))

        # Add current message
        messages.append(LLMMessage(role="user", content=message))

        # Generate response
        add_route_trace("llm")
        has_l4_context = bool(l4_context and l4_context.strip())
        response = llm_factory.generate(messages, has_l4_context=has_l4_context)

        logger.info(
            "query_completed",
            extra={
                "provider": response.provider,
                "model": response.model,
                "usage": response.usage,
            }
        )

        return _success_response({
            "response": response.content,
            "user_type": "office_staff",
            "reasoning_steps": [],
            "meta": {
                "provider": response.provider,
                "model": response.model,
                "fallback_used": response.fallback_used,
            }
        })

    except Exception as e:
        logger.error(f"query_handler_error: {e}")
        return _error_response(500, str(e))


def _get_l1_context(query: str) -> str:
    """Get L1 (industry knowledge) context.

    Note: Implement with your L1 search service.
    """
    add_layer_accessed("L1")

    # Placeholder - implement your L1 search
    # Example:
    # from ..services.l1_rag_service import search_l1
    # results = search_l1(query)
    # return format_results(results)

    return ""


def _get_l3_context(query: str, tenant_id: str) -> str:
    """Get L3 (office knowledge) context.

    Note: Implement with your L3 search service.
    """
    add_layer_accessed("L3")

    # Placeholder - implement your L3 search
    return ""


def _get_l4_context(query: str, tenant_id: str, client_id: Optional[str]) -> str:
    """Get L4 (client-specific) context.

    Note: Implement with your L4 search service.
    """
    if not client_id:
        return ""

    add_layer_accessed("L4")

    # Placeholder - implement your L4 search
    # Example:
    # from ..services.l4_chunks_service import search_l4
    # results = search_l4(query, tenant_id, client_id)
    # return format_results(results)

    return ""


def _get_l5_context(tenant_id: str, client_id: Optional[str], session_id: str) -> str:
    """Get L5 (conversation memory) context.

    Note: Implement with your L5 memory service.
    """
    add_layer_accessed("L5")

    # Placeholder - implement your L5 memory retrieval
    # Example:
    # from ..services.memory_service import get_recent_conversations
    # conversations = get_recent_conversations(tenant_id, client_id, session_id)
    # return format_conversations(conversations)

    return ""


def _get_company_name(client_id: Optional[str]) -> str:
    """Get company name for client.

    Note: Implement with your client service.
    """
    if not client_id:
        return "お客様"

    # Placeholder - implement client lookup
    # from ..services.client_service import get_client_by_id
    # client = get_client_by_id(client_id)
    # return client.name if client else "お客様"

    return "お客様"


def _success_response(data: Dict[str, Any]) -> Dict[str, Any]:
    """Build success response."""
    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "application/json; charset=utf-8"
        },
        "body": json.dumps(data, ensure_ascii=False)
    }


def _error_response(status_code: int, message: str) -> Dict[str, Any]:
    """Build error response."""
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json; charset=utf-8"
        },
        "body": json.dumps({
            "error": message,
            "timestamp": datetime.now().isoformat()
        }, ensure_ascii=False)
    }


# Legacy function for loading company chunks (placeholder)
def load_company_chunks(tenant_id: str) -> List[Dict]:
    """Load company chunks for a tenant.

    Note: Implement with your data loading logic.
    """
    return []
