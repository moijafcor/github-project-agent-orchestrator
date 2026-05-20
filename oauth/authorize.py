"""
GET  /oauth/authorize  — show consent screen
POST /oauth/authorize  — user approves, issue auth code
"""
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urlencode

from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse
from starlette.templating import Jinja2Templates

from . import models

templates = Jinja2Templates(
    directory=str(Path(__file__).parent.parent / "templates")
)

_TOOLS = [
    "list_project_items",
    "list_project_fields",
    "create_project_item",
    "update_project_item_field",
    "archive_project_item",
    "link_issue_to_project",
    "link_pr_to_project",
]


def _get_client(client_id: str):
    with models.get_db() as conn:
        return conn.execute(
            "SELECT * FROM oauth_clients WHERE client_id=?", (client_id,)
        ).fetchone()


async def authorize_get(request: Request) -> HTMLResponse:
    """Show the consent screen."""
    params = request.query_params
    client_id = params.get("client_id")
    redirect_uri = params.get("redirect_uri")
    scope = params.get("scope", "mcp")
    state = params.get("state", "")

    client = _get_client(client_id)
    if not client:
        return templates.TemplateResponse(
            "oauth/error.html",
            {"request": request, "error": "Unknown client"},
            status_code=400,
        )

    registered = json.loads(client["redirect_uris"])
    if redirect_uri not in registered:
        return templates.TemplateResponse(
            "oauth/error.html",
            {"request": request, "error": "Invalid redirect_uri"},
            status_code=400,
        )

    return templates.TemplateResponse(
        "oauth/authorize.html",
        {
            "request": request,
            "client_name": client["name"],
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": scope,
            "state": state,
            "tools": _TOOLS,
        },
    )


async def authorize_post(request: Request) -> RedirectResponse:
    """User approved — issue auth code and redirect."""
    form = await request.form()
    client_id = form.get("client_id")
    redirect_uri = form.get("redirect_uri")
    scope = form.get("scope", "mcp")
    state = form.get("state", "")
    approved = form.get("action") == "approve"

    if not approved:
        params = urlencode({"error": "access_denied", "state": state})
        return RedirectResponse(f"{redirect_uri}?{params}", status_code=302)

    github_token = form.get("github_token", "")
    if not github_token:
        return templates.TemplateResponse(
            "oauth/error.html",
            {"request": request, "error": "GitHub token required"},
            status_code=400,
        )

    user_id = hashlib.sha256(github_token.encode()).hexdigest()[:16]

    # Hold the GitHub token in memory until the token exchange completes
    os.environ[f"_OAUTH_PENDING_{user_id}"] = github_token

    code = models.create_auth_code(client_id, redirect_uri, scope, user_id)
    params = urlencode({"code": code, "state": state})
    return RedirectResponse(f"{redirect_uri}?{params}", status_code=302)
