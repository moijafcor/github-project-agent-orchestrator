"""
Validates Bearer tokens on incoming MCP requests.
Sets GITHUB_TOKEN in env so crud functions pick it up transparently.

Uses a pure ASGI class rather than BaseHTTPMiddleware — the latter buffers
the full response body, which breaks SSE streaming connections.
"""
import os

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from . import models

_MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "https://mcp.moisesjafet.com")
_UNPROTECTED = {"/health", "/.well-known/oauth-protected-resource"}
_WWW_AUTH = (
    f'Bearer realm="{_MCP_SERVER_URL}",'
    f' resource_metadata="{_MCP_SERVER_URL}/.well-known/oauth-protected-resource"'
)


class OAuthMiddleware:
    """Pure ASGI middleware — passes scope/receive/send straight through so SSE works."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)

        if request.url.path in _UNPROTECTED:
            await self.app(scope, receive, send)
            return

        auth = request.headers.get("Authorization", "")

        if not auth.startswith("Bearer "):
            await _deny(scope, receive, send, "Bearer token required")
            return

        token = auth[7:]
        if not models.validate_access_token(token):
            await _deny(scope, receive, send, "Invalid or expired token")
            return

        github_token = models.get_github_token(token)
        if not github_token:
            await _deny(scope, receive, send, "Session expired. Please reconnect.")
            return

        previous = os.environ.get("GITHUB_TOKEN")
        os.environ["GITHUB_TOKEN"] = github_token

        try:
            await self.app(scope, receive, send)
        finally:
            if previous is None:
                os.environ.pop("GITHUB_TOKEN", None)
            else:
                os.environ["GITHUB_TOKEN"] = previous


async def _deny(scope: Scope, receive: Receive, send: Send, message: str) -> None:
    response = JSONResponse(
        {"error": "unauthorized", "message": message},
        status_code=401,
        headers={"WWW-Authenticate": _WWW_AUTH},
    )
    await response(scope, receive, send)
