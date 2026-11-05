"""MCP tools for decky server at /mcp."""

from __future__ import annotations

import logging
from typing import Any, Literal

import click
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from starlette.routing import BaseRoute

from decky import config, github
from decky.commands import pr as pr_cmd
from decky.server import api
from decky.server.views import SettingError, save_setting

log = logging.getLogger(__name__)

PATH = "/mcp"

INSTRUCTIONS = (
    "List the user's pull requests and start a review command configured on the machine. "
    "Read and change decky config. Secrets: none."
)

READ = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)
DELETE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=False)

PrKind = Literal["review", "team", "mine"]


def list_prs(kind: PrKind, show_all: bool = False) -> dict[str, Any]:
    if kind not in pr_cmd.KINDS:
        raise ToolError(f"kind must be one of {', '.join(pr_cmd.KINDS)}")
    lists, notes = github.load_pr_lists()
    prs = lists[kind]
    if show_all:
        rows = prs
        hidden = 0
    else:
        rows, hidden = pr_cmd.filter_prs(prs, False)
    from decky.server import views

    return {
        "rows": [views.pr_row(p) for p in rows],
        "hidden": hidden,
        "notes": notes,
    }


def start_review(state: api.State, repo: str, number: int) -> dict[str, str]:
    with state.lock:
        try:
            pr_cmd.open_review(repo, number)
        except click.ClickException as e:
            raise ToolError(str(e)) from e
    return {"message": f"opened {repo}#{number} for review"}


def list_config() -> list[dict[str, Any]]:
    from decky.server import views

    return views.config_settings()


def get_config(key: str) -> Any:
    try:
        config.setting(key)
    except click.BadParameter as e:
        raise ToolError(str(e)) from e
    value, source = config.resolve(key)
    return {"key": key, "value": value, "source": source}


def set_config(key: str, value: str) -> str:
    try:
        return save_setting(key, value, unset=False)
    except SettingError as e:
        raise ToolError(str(e)) from e


def unset_config(key: str) -> str:
    try:
        return save_setting(key, "", unset=True)
    except SettingError as e:
        raise ToolError(str(e)) from e


def build(state: api.State | None = None) -> MCPServer:
    decky_state = state or api.State()
    server = MCPServer("decky", instructions=INSTRUCTIONS)

    @server.tool(annotations=READ)
    def list_prs_tool(kind: PrKind, show_all: bool = False) -> dict[str, Any]:
        return list_prs(kind, show_all)

    @server.tool(annotations=WRITE)
    def start_review_tool(repo: str, number: int) -> dict[str, str]:
        return start_review(decky_state, repo, number)

    @server.tool(annotations=READ)
    def list_config_tool() -> list[dict[str, Any]]:
        return list_config()

    @server.tool(annotations=READ)
    def get_config_tool(key: str) -> Any:
        return get_config(key)

    @server.tool(annotations=WRITE)
    def set_config_tool(key: str, value: str) -> str:
        return set_config(key, value)

    @server.tool(annotations=DELETE)
    def unset_config_tool(key: str) -> str:
        return unset_config(key)

    return server


def routes(server: MCPServer, host: str) -> list[BaseRoute]:
    app = server.streamable_http_app(
        streamable_http_path=PATH,
        stateless_http=True,
        json_response=True,
        host=host,
    )
    return list(app.routes)
