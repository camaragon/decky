"""FastAPI application for decky server."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

import click

from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from decky import config
from decky.server.api import ActionFailed, State, allowed_hosts, local_host, proxy_host, router
from decky.server import mcp as mcp_mod

log = logging.getLogger(__name__)

STATIC = Path(__file__).parent / "static"
PROXY_ROUTES = {
    ("GET", "/api/meta"),
    ("GET", "/api/config"),
    ("GET", "/api/tables/review"),
    ("GET", "/api/tables/team"),
    ("GET", "/api/tables/mine"),
    ("GET", "/api/queue"),
    ("GET", "/api/status"),
    ("GET", "/api/inbox"),
    ("GET", "/api/inbox/image"),
    ("POST", "/api/inbox/decision"),
}
MISSING = "the web app is not built; run `pnpm -C web install && pnpm -C web build`"


def create_app(
    state: State | None = None,
    static: Path | None = STATIC,
    host: str = "127.0.0.1",
) -> FastAPI:
    """Build the decky server app including /mcp tools."""
    decky_state = state or State(listen_host=host)
    decky_state.allowed_hosts = allowed_hosts(config.resolve("server.allowed_hosts")[0] or [])
    tools = mcp_mod.build(decky_state)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with tools.session_manager.run():
            yield

    app = FastAPI(
        title="decky",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.decky = decky_state

    @app.middleware("http")
    async def validate_api_host(request: Request, call_next):
        path = request.url.path
        api = path == "/api" or path.startswith("/api/")
        if local_host(request):
            return await call_next(request)
        if not proxy_host(request):
            if api:
                return JSONResponse({"message": "host not allowed"}, status_code=421)
            return await call_next(request)
        if request.method == "POST" and path == "/api/inbox/decision":
            if (
                request.headers.getlist("origin") != [str(request.base_url).rstrip("/")]
                or request.headers.get("sec-fetch-site") not in {None, "same-origin"}
                or request.headers.get("x-requested-with") != "fetch"
            ):
                return JSONResponse(
                    {"message": "Inbox answers require a same-origin request"}, status_code=403
                )
        if (request.method, path) in PROXY_ROUTES or (
            request.method in {"GET", "HEAD"} and not api and not path.startswith("/mcp")
        ):
            return await call_next(request)
        return JSONResponse(
            {"message": "This action is unavailable through an allowed proxy host; use local access."},
            status_code=403,
        )

    @app.exception_handler(click.ClickException)
    @app.exception_handler(ActionFailed)
    async def action_failed(request: Request, exc: ActionFailed):
        if not local_host(request) and proxy_host(request):
            return JSONResponse(
                {"message": "Unable to load data; check the server configuration locally."},
                status_code=422,
            )
        return JSONResponse({"message": str(exc)}, status_code=422)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        if request.url.path.startswith("/api"):
            return JSONResponse(
                {"message": str(exc.detail)}, status_code=exc.status_code
            )
        return await http_exception_handler(request, exc)

    @app.exception_handler(RequestValidationError)
    async def bad_input(_request: Request, exc: RequestValidationError):
        problems = "; ".join(
            f"{'.'.join(str(p) for p in e['loc'][1:])}: {e['msg']}"
            for e in exc.errors()
        )
        return JSONResponse({"message": problems or "bad input"}, status_code=400)

    from decky.server.inbox import router as inbox_router
    app.include_router(inbox_router)
    app.include_router(router)
    app.router.routes.extend(mcp_mod.routes(tools, host))

    if static is not None:

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            if path.startswith("api/"):
                raise HTTPException(404, f"no route /{path}")
            index = static / "index.html"
            if not index.is_file():
                return PlainTextResponse(MISSING, status_code=503)
            found = (static / path).resolve()
            static_root = static.resolve()
            if path and found.is_file() and found.is_relative_to(static_root):
                return FileResponse(found)
            return FileResponse(index, headers={"Cache-Control": "no-cache"})

    return app
