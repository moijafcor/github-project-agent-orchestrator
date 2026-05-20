"""
POST /oauth/token — authorization_code and refresh_token grant types
"""
import os
import time

from starlette.requests import Request
from starlette.responses import JSONResponse

from . import models


async def token_endpoint(request: Request) -> JSONResponse:
    form = await request.form()
    grant_type = form.get("grant_type")

    if grant_type == "authorization_code":
        return await _handle_auth_code(form)
    elif grant_type == "refresh_token":
        return await _handle_refresh(form)
    else:
        return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)


async def _handle_auth_code(form) -> JSONResponse:
    code = form.get("code")
    client_id = form.get("client_id")
    client_secret = form.get("client_secret")
    redirect_uri = form.get("redirect_uri")

    with models.get_db() as conn:
        client = conn.execute(
            "SELECT * FROM oauth_clients WHERE client_id=? AND client_secret=?",
            (client_id, client_secret),
        ).fetchone()

    if not client:
        return JSONResponse({"error": "invalid_client"}, status_code=401)

    auth_code = models.consume_auth_code(code)
    if not auth_code:
        return JSONResponse({"error": "invalid_grant"}, status_code=400)

    if auth_code["redirect_uri"] != redirect_uri:
        return JSONResponse({"error": "invalid_grant"}, status_code=400)

    user_id = auth_code["user_id"]
    github_token = os.environ.pop(f"_OAUTH_PENDING_{user_id}", None)

    if not github_token:
        return JSONResponse({"error": "invalid_grant"}, status_code=400)

    access_token, refresh_token = models.create_access_token(
        client_id, user_id, auth_code["scope"]
    )

    # Associate GitHub token with this access token for MCP tool calls
    os.environ[f"_GITHUB_TOKEN_{access_token}"] = github_token

    return JSONResponse({
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": 3600,
        "refresh_token": refresh_token,
        "scope": auth_code["scope"],
    })


async def _handle_refresh(form) -> JSONResponse:
    refresh_token = form.get("refresh_token")
    client_id = form.get("client_id")
    client_secret = form.get("client_secret")

    with models.get_db() as conn:
        client = conn.execute(
            "SELECT * FROM oauth_clients WHERE client_id=? AND client_secret=?",
            (client_id, client_secret),
        ).fetchone()
        if not client:
            return JSONResponse({"error": "invalid_client"}, status_code=401)

        rt = conn.execute(
            "SELECT * FROM refresh_tokens WHERE token=? AND expires_at>?",
            (refresh_token, int(time.time())),
        ).fetchone()
        if not rt:
            return JSONResponse({"error": "invalid_grant"}, status_code=400)

    new_access, new_refresh = models.create_access_token(
        rt["client_id"], rt["user_id"], "mcp"
    )

    old_github_token = os.environ.pop(f"_GITHUB_TOKEN_{rt['access_token']}", None)
    if old_github_token:
        os.environ[f"_GITHUB_TOKEN_{new_access}"] = old_github_token

    return JSONResponse({
        "access_token": new_access,
        "token_type": "Bearer",
        "expires_in": 3600,
        "refresh_token": new_refresh,
        "scope": "mcp",
    })
