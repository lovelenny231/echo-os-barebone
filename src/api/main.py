"""
ECHO OS Barebone - FastAPI Main Application

Generic multi-tenant RAG/LLM platform.
Customize SERVICE_NAME, PERSONA_NAME, and prompts for your use case.
"""

import os
import json
import uuid
import secrets
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Literal

from fastapi import FastAPI, HTTPException, Request, Depends, Form, Cookie
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel

from .query_handler import lambda_handler, load_company_chunks
from .security_middleware import (
    limiter,
    SecurityHeadersMiddleware,
    CacheControlMiddleware,
    _rate_limit_exceeded_handler,
)
from slowapi.errors import RateLimitExceeded
from .middleware.host_resolver import HostResolverMiddleware, get_tenant_slug_from_request

from ..utils.env import env
from ..services.legacy_resolver import resolve_to_context, normalize_for_query, is_legacy_format
from ..services import tenant_service, client_service
from ..models.tenant import TenantContext
from .deps import get_tenant_context, get_tenant_context_from_jwt
from ..core.logging import get_logger, set_context, clear_context, add_route_trace, add_layer_accessed, get_context, get_trace_id

logger = get_logger(__name__)

# =============================================================================
# Service Identity (from environment)
# =============================================================================
SERVICE_NAME = env.SERVICE_NAME
OFFICE_NAME = env.OFFICE_NAME
DEFAULT_OFFICE_ID = env.DEFAULT_OFFICE_ID

# Legacy tenant configuration (for backward compatibility)
TENANTS = [
    {"slug": "demo", "id": "1", "name": "Demo Tenant"},
]


def normalize_tenant_id(tenant_input: str) -> str:
    """Normalize tenant ID."""
    if tenant_input.startswith("t_"):
        return tenant_input

    for tenant in TENANTS:
        if tenant["slug"] == tenant_input or tenant["id"] == tenant_input:
            return tenant["id"]
    return "1"


# =============================================================================
# FastAPI Application
# =============================================================================

app = FastAPI(
    title=f"{SERVICE_NAME}",
    description="Multi-tenant RAG/LLM Platform",
    version="1.0.0",
    default_response_class=JSONResponse
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security middlewares
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CacheControlMiddleware)

# Host-based tenant resolution
app.add_middleware(HostResolverMiddleware)

# Rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# =============================================================================
# TraceableRequest Middleware
# =============================================================================

@app.middleware("http")
async def traceable_request_middleware(request: Request, call_next):
    """Add trace_id to all requests for traceability."""
    trace_id = str(uuid.uuid4())
    start_time = time.time()

    request.state.trace_id = trace_id
    request.state.start_time = start_time
    request.state.correlation_id = trace_id[:8]

    set_context(trace_id=trace_id, start_time=start_time)
    add_route_trace("gateway")

    # Kill-switch check
    if os.getenv("DISABLE_EXTERNAL", "false").lower() == "true":
        if request.url.path.startswith("/chat"):
            clear_context()
            return JSONResponse(
                status_code=503,
                content={"error": "Service temporarily disabled by administrator"}
            )

    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")[:100]

    logger.info(
        "request_start",
        extra={
            "event_type": "request_start",
            "method": request.method,
            "path": request.url.path,
            "client_ip": client_ip,
            "user_agent": user_agent,
        }
    )

    try:
        response = await call_next(request)
    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        ctx = get_context()
        logger.error(
            "request_error",
            extra={
                "event_type": "request_error",
                "method": request.method,
                "path": request.url.path,
                "duration_ms": duration_ms,
                "error": str(e),
                "route_trace": ctx.get("route_trace", []),
                "layers_accessed": ctx.get("layers_accessed", []),
            }
        )
        clear_context()
        raise

    duration_ms = int((time.time() - start_time) * 1000)
    ctx = get_context()

    logger.info(
        "request_end",
        extra={
            "event_type": "request_end",
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
            "route_trace": ctx.get("route_trace", []),
            "layers_accessed": ctx.get("layers_accessed", []),
        }
    )

    response.headers["X-Trace-ID"] = trace_id
    response.headers["X-Correlation-ID"] = trace_id[:8]

    git_tag = os.getenv("GIT_TAG", "")
    git_sha = os.getenv("GIT_SHA", "")

    if git_tag:
        response.headers["X-Release"] = git_tag
    if git_sha:
        response.headers["X-Commit"] = git_sha[:8]

    clear_context()
    return response


# =============================================================================
# Request Models
# =============================================================================

class ChatRequest(BaseModel):
    message: str
    user_id: Optional[str] = "anonymous"
    session_id: Optional[str] = "default"
    tenant_id: Optional[str] = "1"
    client_id: Optional[str] = None
    conversation_history: Optional[List[Dict[str, str]]] = []
    debug_mode: Optional[bool] = False


class ChatResponse(BaseModel):
    response: str
    user_type: Literal["office_staff", "client"] = "office_staff"
    tenant_id: str
    timestamp: str
    status: str = "success"
    meta: Optional[Dict[str, Any]] = None
    reasoning_steps: Optional[List[str]] = None


# =============================================================================
# Health Check
# =============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    health_data = {
        "status": "healthy",
        "service": SERVICE_NAME,
        "version": "1.0.0",
        "timestamp": datetime.now().isoformat(),
        "git_tag": os.getenv("GIT_TAG", "dev"),
        "git_sha": os.getenv("GIT_SHA", "unknown")[:8],
        "layers": {
            "l1_enabled": env.L1_ENABLED,
            "l3_enabled": env.L3_ENABLED,
            "l4_enabled": env.L4_ENABLED,
            "l5_enabled": env.L5_ENABLED,
        }
    }

    return health_data


# =============================================================================
# Chat Endpoints
# =============================================================================

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """Main chat endpoint."""
    try:
        lambda_event = {
            "httpMethod": "POST",
            "body": json.dumps({
                "message": request.message,
                "user_id": request.user_id,
                "session_id": request.session_id,
                "tenant_id": normalize_tenant_id(request.tenant_id or "1"),
                "client_id": request.client_id,
                "conversation_history": request.conversation_history
            }),
            "headers": {
                "Content-Type": "application/json"
            }
        }

        lambda_context = {}
        result = lambda_handler(lambda_event, lambda_context)

        if result.get("statusCode") == 200:
            response_body = json.loads(result["body"])

            if isinstance(response_body, dict):
                response_text = response_body.get("response", "")
            else:
                response_text = str(response_body)

            user_type = response_body.get("user_type", "office_staff") if isinstance(response_body, dict) else "office_staff"
            reasoning_steps = response_body.get("reasoning_steps", []) if isinstance(response_body, dict) else []

            return ChatResponse(
                response=response_text,
                user_type=user_type,
                tenant_id=normalize_tenant_id(request.tenant_id or "1"),
                timestamp=datetime.now().isoformat(),
                status="success",
                meta={
                    "session_id": request.session_id,
                    "user_id": request.user_id
                },
                reasoning_steps=reasoning_steps
            )
        else:
            error_body = json.loads(result.get("body", "{}"))
            raise HTTPException(
                status_code=result.get("statusCode", 500),
                detail=error_body.get("message", "Unknown error")
            )

    except Exception as e:
        logger.error(f"Chat endpoint error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


@app.post("/chat/office")
async def chat_office_endpoint(
    request: Request,
    ctx: TenantContext = Depends(get_tenant_context)
):
    """Office chat endpoint with tenant context."""
    try:
        body = await request.json()
        effective_tenant_id = normalize_for_query(ctx.tenant_id, ctx.client_id)

        logger.info(
            "chat_office_request",
            extra={
                "tenant_id": ctx.tenant_id,
                "client_id": ctx.client_id,
                "effective_tenant_id": effective_tenant_id,
                "source": ctx.source,
            }
        )

        lambda_event = {
            "httpMethod": "POST",
            "body": json.dumps({
                "message": body.get("message", ""),
                "user_id": body.get("user_id", "anonymous"),
                "session_id": body.get("session_id", "default"),
                "tenant_id": effective_tenant_id,
                "client_id": ctx.client_id,
                "conversation_history": body.get("conversation_history", [])
            }),
            "headers": {
                "Content-Type": "application/json"
            }
        }

        lambda_context = {}
        result = lambda_handler(lambda_event, lambda_context)

        if result.get("statusCode") == 200:
            response_body = json.loads(result["body"])

            if isinstance(response_body, dict):
                response_text = response_body.get("response", "")
            else:
                response_text = str(response_body)

            user_type = response_body.get("user_type", "office_staff") if isinstance(response_body, dict) else "office_staff"
            reasoning_steps = response_body.get("reasoning_steps", []) if isinstance(response_body, dict) else []

            return ChatResponse(
                response=response_text,
                user_type=user_type,
                tenant_id=effective_tenant_id,
                timestamp=datetime.now().isoformat(),
                status="success",
                meta={
                    "session_id": body.get("session_id", "default"),
                    "user_id": body.get("user_id", "anonymous"),
                    "client_id": ctx.client_id
                },
                reasoning_steps=reasoning_steps
            )
        else:
            error_body = json.loads(result.get("body", "{}"))
            raise HTTPException(
                status_code=result.get("statusCode", 500),
                detail=error_body.get("message", error_body.get("error", "Unknown error"))
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"chat_office_error: {e}", extra={"error": str(e)})
        raise HTTPException(status_code=400, detail=f"Invalid request: {str(e)}")


# =============================================================================
# Static Files and Frontend
# =============================================================================

# Mount static files if directory exists
import pathlib
frontend_dir = pathlib.Path("frontend")
if frontend_dir.exists():
    app.mount("/static", StaticFiles(directory="frontend"), name="static")


@app.get("/", response_class=HTMLResponse)
async def read_root():
    """Serve frontend HTML."""
    try:
        with open("frontend/index.html", "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read(), media_type="text/html; charset=utf-8")
    except FileNotFoundError:
        return HTMLResponse(
            content=f"<h1>{SERVICE_NAME}</h1><p>Frontend not configured. See /health for API status.</p>",
            status_code=200,
            media_type="text/html; charset=utf-8"
        )


# =============================================================================
# Admin Portal
# =============================================================================

_admin_sessions: Dict[str, datetime] = {}
ADMIN_SESSION_DURATION_HOURS = 8
ADMIN_SESSION_COOKIE_NAME = "admin_session"
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "")


def _verify_admin_session(session_token: str) -> bool:
    """Verify admin session token."""
    if not session_token or session_token not in _admin_sessions:
        return False
    expires_at = _admin_sessions[session_token]
    if datetime.now() > expires_at:
        del _admin_sessions[session_token]
        return False
    return True


def _create_admin_session() -> str:
    """Create admin session."""
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now() + timedelta(hours=ADMIN_SESSION_DURATION_HOURS)
    _admin_sessions[token] = expires_at
    return token


def _get_admin_login_html(return_url: str = "/admin") -> str:
    """Return admin login HTML."""
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Admin Login - {SERVICE_NAME}</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        .login-container {{
            background: white;
            padding: 40px;
            border-radius: 16px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            max-width: 400px;
            width: 90%;
        }}
        h1 {{ color: #333; margin-bottom: 8px; font-size: 24px; }}
        .subtitle {{ color: #666; margin-bottom: 24px; font-size: 14px; }}
        .form-group {{ margin-bottom: 20px; }}
        label {{ display: block; margin-bottom: 8px; color: #555; font-weight: 500; }}
        input[type="password"] {{
            width: 100%;
            padding: 12px 16px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-size: 16px;
        }}
        input[type="password"]:focus {{ outline: none; border-color: #667eea; }}
        button {{
            width: 100%;
            padding: 14px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
        }}
        button:hover {{ transform: translateY(-2px); box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4); }}
        .error {{ background: #fee; color: #c00; padding: 12px; border-radius: 8px; margin-bottom: 20px; display: none; }}
        .error.show {{ display: block; }}
    </style>
</head>
<body>
    <div class="login-container">
        <h1>Admin Login</h1>
        <p class="subtitle">{SERVICE_NAME} Management Console</p>
        <div class="error" id="error">Invalid admin key</div>
        <form method="POST" action="/admin/login">
            <div class="form-group">
                <label for="admin_key">Admin Key</label>
                <input type="password" id="admin_key" name="admin_key" placeholder="Enter ADMIN_API_KEY" required>
            </div>
            <button type="submit">Login</button>
        </form>
    </div>
    <script>
        if (window.location.search.includes('error=1')) {{
            document.getElementById('error').classList.add('show');
        }}
    </script>
</body>
</html>"""


@app.get("/admin", response_class=HTMLResponse)
async def admin_portal(admin_session: Optional[str] = Cookie(None)):
    """Admin portal."""
    if not ADMIN_API_KEY:
        env_mode = os.getenv("ENV", "dev")
        if env_mode in ("dev", "staging"):
            try:
                with open("frontend/admin.html", "r", encoding="utf-8") as f:
                    return HTMLResponse(content=f.read(), media_type="text/html; charset=utf-8")
            except FileNotFoundError:
                return HTMLResponse(
                    content=f"<h1>{SERVICE_NAME} Admin</h1><p>Admin panel not configured.</p>",
                    status_code=200
                )

    if not _verify_admin_session(admin_session):
        return HTMLResponse(content=_get_admin_login_html(), media_type="text/html; charset=utf-8")

    try:
        with open("frontend/admin.html", "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read(), media_type="text/html; charset=utf-8")
    except FileNotFoundError:
        return HTMLResponse(
            content=f"<h1>{SERVICE_NAME} Admin</h1><p>Admin panel not configured.</p>",
            status_code=200
        )


@app.post("/admin/login")
async def admin_login(admin_key: str = Form(...)):
    """Admin login."""
    if not ADMIN_API_KEY:
        env_mode = os.getenv("ENV", "dev")
        if env_mode in ("dev", "staging"):
            response = RedirectResponse(url="/admin", status_code=303)
            session_token = _create_admin_session()
            response.set_cookie(
                key=ADMIN_SESSION_COOKIE_NAME,
                value=session_token,
                httponly=True,
                secure=True,
                samesite="lax",
                max_age=ADMIN_SESSION_DURATION_HOURS * 3600
            )
            return response

    if admin_key != ADMIN_API_KEY:
        return RedirectResponse(url="/admin?error=1", status_code=303)

    response = RedirectResponse(url="/admin", status_code=303)
    session_token = _create_admin_session()
    response.set_cookie(
        key=ADMIN_SESSION_COOKIE_NAME,
        value=session_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=ADMIN_SESSION_DURATION_HOURS * 3600
    )
    return response


@app.post("/admin/logout")
async def admin_logout(admin_session: Optional[str] = Cookie(None)):
    """Admin logout."""
    if admin_session and admin_session in _admin_sessions:
        del _admin_sessions[admin_session]

    response = RedirectResponse(url="/admin", status_code=303)
    response.delete_cookie(key=ADMIN_SESSION_COOKIE_NAME)
    return response


# =============================================================================
# Utility Endpoints
# =============================================================================

@app.get("/tenants")
async def list_tenants():
    """List available tenants."""
    return {
        "tenants": TENANTS,
        "default_tenant": "1"
    }


@app.get("/debug/headers")
async def debug_headers(request: Request):
    """Debug endpoint for headers."""
    return {
        "host": request.headers.get("host", ""),
        "x-forwarded-host": request.headers.get("x-forwarded-host", ""),
        "tenant_slug": getattr(request.state, "tenant_slug", None),
    }


# =============================================================================
# RAG Status
# =============================================================================

@app.get("/rag/status")
async def rag_status():
    """RAG system status."""
    return {
        "status": "active",
        "timestamp": datetime.now().isoformat(),
        "service": SERVICE_NAME,
        "layers": {
            "l1": {"enabled": env.L1_ENABLED, "backend": "azure" if env.L1_USE_AZURE_AI_SEARCH else "faiss"},
            "l3": {"enabled": env.L3_ENABLED},
            "l4": {"enabled": env.L4_ENABLED, "backend": "azure" if env.L4_USE_AZURE_AI_SEARCH else "dynamodb"},
            "l5": {"enabled": env.L5_ENABLED},
        }
    }


# =============================================================================
# Startup
# =============================================================================

@app.on_event("startup")
async def startup():
    """Application startup."""
    logger.info(f"Starting {SERVICE_NAME}")
    logger.info(f"L1 Enabled: {env.L1_ENABLED}")
    logger.info(f"L4 Enabled: {env.L4_ENABLED}")
    logger.info(f"L5 Enabled: {env.L5_ENABLED}")


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
