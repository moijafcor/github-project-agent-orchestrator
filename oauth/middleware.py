"""
Validates Bearer tokens on incoming MCP requests.
Sets GITHUB_TOKEN in env so crud functions pick it up transparently.
"""
import os

from starlette.requests import Request
from starlette.responses import JSONResponse

from . import models

_MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "https://mcp.moisesjafet.com")
_UNPROTECTED = {"/health", "/.well-known/oauth-protected-resource"}
_WWW_AUTH = (
    f'Bearer realm="{_MCP_SERVER_URL}",'
    f' resource_metadata="{_MCP_SERVER_URL}/.well-known/oauth-protected-resource"'
)


async def require_oauth_token(request: Request, call_next):
    """
    Starlette BaseHTTPMiddleware dispatch function.
    Validates Bearer token and sets GITHUB_TOKEN for the duration of the request.
    """
    if request.url.path in _UNPROTECTED:
        return await call_next(request)

    auth = request.headers.get("Authorization", "")

    if not auth.startswith("Bearer "):
        return JSONResponse(
            {"error": "unauthorized", "message": "Bearer token required"},
            status_code=401,
            headers={"WWW-Authenticate": _WWW_AUTH},
        )

    token = auth[7:]
    token_row = models.validate_access_token(token)

    if not token_row:
        return JSONResponse(
            {"error": "unauthorized", "message": "Invalid or expired token"},
            status_code=401,
            headers={"WWW-Authenticate": _WWW_AUTH},
        )

    github_token = models.get_github_token(token)
    if not github_token:
        return JSONResponse(
            {"error": "unauthorized", "message": "Session expired. Please reconnect."},
            status_code=401,
            headers={"WWW-Authenticate": _WWW_AUTH},
        )

    # Set GITHUB_TOKEN so crud functions pick it up; restore after request
    previous = os.environ.get("GITHUB_TOKEN")
    os.environ["GITHUB_TOKEN"] = github_token
    request.state.github_token = github_token
    request.state.user_id = token_row["user_id"]

    try:
        response = await call_next(request)
    finally:
        if previous is None:
            os.environ.pop("GITHUB_TOKEN", None)
        else:
            os.environ["GITHUB_TOKEN"] = previous

    return response
