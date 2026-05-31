#!/usr/bin/env python3
"""
OAuth 2.0 authorization server for the GitHub Projects MCP orchestrator.
Runs alongside mcp_server.py (this server on port 8766, MCP on port 8765).

Usage:
  python scripts/oauth_server.py [--host 0.0.0.0] [--port 8766]

Register as a Claude custom connector:
  MCP URL:              https://mcp.moisesjafet.com/sse
  OAuth Client ID:      from .env OAUTH_CLIENT_ID
  OAuth Client Secret:  from .env OAUTH_CLIENT_SECRET
  Authorization URL:    https://oauth.moisesjafet.com/oauth/authorize
  Token URL:            https://oauth.moisesjafet.com/oauth/token
"""
import argparse
import sys
from contextlib import asynccontextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

import os

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.routing import Route

from oauth.authorize import authorize_get, authorize_post
from oauth.models import create_client, init_db
from oauth.token import token_endpoint


@asynccontextmanager
async def lifespan(app):
    init_db()
    create_client(
        client_id=os.environ["OAUTH_CLIENT_ID"],
        client_secret=os.environ["OAUTH_CLIENT_SECRET"],
        redirect_uris=[
            "https://claude.ai/api/mcp/auth_callback",
            "http://localhost:8766/callback",
        ],
        name="GitHub Projects Orchestrator",
    )
    yield


app = Starlette(
    debug=False,
    lifespan=lifespan,
    routes=[
        Route("/oauth/authorize", authorize_get,   methods=["GET"]),
        Route("/oauth/authorize", authorize_post,  methods=["POST"]),
        Route("/oauth/token",     token_endpoint,  methods=["POST"]),
    ],
    middleware=[
        Middleware(
            SessionMiddleware,
            secret_key=os.environ.get("SESSION_SECRET", os.urandom(32).hex()),
        )
    ],
)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OAuth 2.0 authorization server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()

    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port)
