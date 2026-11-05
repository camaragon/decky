"""FastAPI application for decky server."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from decky.server.api import ActionFailed, State, router
from decky.server import mcp as mcp_mod

log = logging.getLogger(__name__)

STATIC = Path(__file__).parent / "static"
MISSING = "the web app is not built; run `pnpm -C web install && pnpm -C web build`"


def create_app(
    state: State | None = None,
    static: Path | None = STATIC,
    host: str = "127.0.0.1",
) -> FastAPI:
    """Build the decky server app including /mcp tools."""
    decky_state = state or State(listen_host=host)
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

    @app.exception_handler(ActionFailed)
    async def action_failed(_request: Request, exc: ActionFailed):
        return JSONResponse({"message": str(exc)}, status_code=422)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        if request.url.path.startswith("/api"):
            return JSONResponse({"message": str(exc.detail)}, status_code=exc.status_code)
        return await http_exception_handler(request, exc)

    @app.exception_handler(RequestValidationError)
    async def bad_input(_request: Request, exc: RequestValidationError):
        problems = "; ".join(
            f"{'.'.join(str(p) for p in e['loc'][1:])}: {e['msg']}" for e in exc.errors()
        )
        return JSONResponse({"message": problems or "bad input"}, status_code=400)

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
