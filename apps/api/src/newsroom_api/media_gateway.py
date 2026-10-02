"""Media-only public entry point for local publishing.

Instagram has to fetch post media from a public HTTPS address. Tunnelling the
whole API for that would also publish the desk's management routes, docs and
Instagram status to the internet. This app serves exactly one route,
``/api/public/media/{token}.{jpg|mp4}``, with the same rules as the API, and
answers 404 to everything else. It has no docs, no OpenAPI schema and never
writes to the database.

Run it next to the API and point the tunnel at it instead of at the API::

    uv run uvicorn newsroom_api.media_gateway:app --host 127.0.0.1 --port 8090 --env-file ..\\..\\infra\\.env
    cloudflared tunnel --url http://127.0.0.1:8090
"""

from __future__ import annotations

from typing import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse

from .config import Settings
from .database import Repository
from .public_media import serve_public_media

_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
}


def create_media_gateway(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or Settings.from_env()
    repository = Repository(app_settings.database_path)

    gateway = FastAPI(
        title="Giani media gateway",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    gateway.state.settings = app_settings
    gateway.state.repository = repository

    @gateway.middleware("http")
    async def security_headers(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)
        for name, value in _SECURITY_HEADERS.items():
            response.headers[name] = value
        return response

    @gateway.api_route(
        "/api/public/media/{filename}", methods=["GET", "HEAD"]
    )
    def public_media(filename: str) -> FileResponse:
        return serve_public_media(app_settings, repository, filename)

    return gateway


app = create_media_gateway()
