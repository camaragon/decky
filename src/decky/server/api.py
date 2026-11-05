"""JSON API for decky server."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

import click
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from decky import config
from decky.browser import open_http_url
from decky.commands import pr as pr_cmd
from decky.server import views
from decky.status import load_status
from decky.queue import load_queue

TABLES = pr_cmd.KINDS


class ActionFailed(Exception):
    """An action failed; the client reads message."""


@dataclass
class State:
    lock: threading.RLock = field(default_factory=threading.RLock)
    listen_host: str = "127.0.0.1"


def state(request: Request) -> State:
    return request.app.state.decky


router = APIRouter(prefix="/api")


def allowed_host(request: Request) -> bool:
    host_header = (request.headers.get("host") or "").split(":")[0].lower()
    if not host_header:
        return False
    listen = state(request).listen_host.lower()
    if host_header in {listen, "localhost", "127.0.0.1", "::1", "[::1]"}:
        return True
    if listen in ("0.0.0.0", "::") and host_header in {"localhost", "127.0.0.1", "::1", "[::1]"}:
        return True
    return False


def require_local_host(request: Request) -> None:
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    if not allowed_host(request):
        raise HTTPException(421, "host not allowed")


@router.get("/meta")
def meta() -> dict:
    review, _ = config.resolve("review.command")
    queue, _ = config.resolve("queue.command")
    status, _ = config.resolve("status.command")
    jira, _ = config.resolve("jira.browse_url")
    return {
        "reviewConfigured": bool(review),
        "queueConfigured": bool(queue),
        "statusConfigured": bool(status),
        "jiraBrowseUrl": jira if isinstance(jira, str) and jira.strip() else None,
    }


@router.get("/tables/{kind}")
def table(kind: str) -> dict:
    if kind not in TABLES:
        raise HTTPException(404, f"no table {kind}")
    try:
        return views.fetch_table(kind)
    except click.ClickException as e:
        raise ActionFailed(str(e)) from e


class PrBody(BaseModel):
    repo: str
    number: int


@router.post("/prs/review")
def review_pr(body: PrBody, request: Request) -> dict:
    require_local_host(request)
    with state(request).lock:
        try:
            pr_cmd.open_review(body.repo, body.number)
        except click.ClickException as e:
            raise ActionFailed(str(e)) from e
    return {"message": f"opened {body.repo}#{body.number} for review"}


@router.get("/queue")
def queue_route() -> dict:
    try:
        return load_queue()
    except click.ClickException as e:
        raise ActionFailed(str(e)) from e


@router.get("/status")
def status_route() -> dict:
    try:
        return load_status()
    except click.ClickException as e:
        raise ActionFailed(str(e)) from e


class UrlBody(BaseModel):
    url: str


@router.post("/open-url")
def open_url(body: UrlBody, request: Request) -> dict:
    require_local_host(request)
    if not body.url.startswith(("http://", "https://")):
        raise HTTPException(400, "url must start with http:// or https://")
    with state(request).lock:
        try:
            open_http_url(body.url)
        except click.ClickException as e:
            raise ActionFailed(str(e)) from e
    return {"message": "opened url"}


@router.get("/config")
def get_config() -> dict:
    return {"path": str(config.config_path()), "settings": views.config_settings()}


class ValueBody(BaseModel):
    value: str = ""


@router.put("/config/{key}")
def set_config(key: str, body: ValueBody, request: Request) -> dict:
    require_local_host(request)
    try:
        config.setting(key)
    except click.BadParameter as e:
        raise HTTPException(400, str(e)) from e
    with state(request).lock:
        try:
            message = views.save_setting(key, body.value, unset=False)
        except views.SettingError as e:
            raise ActionFailed(str(e)) from e
    return {"message": message}


@router.delete("/config/{key}")
def unset_config(key: str, request: Request) -> dict:
    require_local_host(request)
    try:
        config.setting(key)
    except click.BadParameter as e:
        raise HTTPException(400, str(e)) from e
    with state(request).lock:
        try:
            message = views.save_setting(key, "", unset=True)
        except views.SettingError as e:
            raise ActionFailed(str(e)) from e
    return {"message": message}
