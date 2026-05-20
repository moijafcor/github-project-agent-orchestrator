"""
Validates Bearer tokens on incoming MCP requests.
Sets GITHUB_TOKEN in env so crud functions pick it up transparently.
"""
import os

from starlette.requests import Request
from starlette.responses import JSONResponse

from . import models


async def require_oauth_token(request: Request, call_next):
    """
    Starlette BaseHTTPMiddleware dispatch function.
    Validates Bearer token and sets GITHUB_TOKEN for the duration of the request.
    """
    # Health / meta endpoints don't require auth
    if request.url.path in ("/health",):
        return await call_next(request)

    auth = request.headers.get("Authorization", "")

    if not auth.startswith("Bearer "):
        return JSONResponse(
            {"error": "unauthorized", "message": "Bearer token required"},
            status_code=401,
        )

    token = auth[7:]
    token_row = models.validate_access_token(token)

    if not token_row:
        return JSONResponse(
            {"error": "unauthorized", "message": "Invalid or expired token"},
            status_code=401,
        )

    github_token = os.environ.get(f"_GITHUB_TOKEN_{token}")
    if not github_token:
        return JSONResponse(
            {"error": "unauthorized", "message": "Session expired. Please reconnect."},
            status_code=401,
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
