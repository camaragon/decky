"""JSON API for decky server."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from ipaddress import ip_address
from urllib.parse import urlsplit

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
    inbox_rows: dict = field(default_factory=dict)
    allowed_hosts: set[str] = field(default_factory=set)

    def save_setting(self, key: str, value: str, *, unset: bool = False) -> str:
        """Serialize read-modify-write operations within this server instance."""
        with self.lock:
            return views.save_setting(key, value, unset=unset)


def state(request: Request) -> State:
    return request.app.state.decky


router = APIRouter(prefix="/api")


def _normalize_host(host: str) -> str:
    try:
        return ip_address(host).compressed
    except ValueError:
        return host.lower()


def allowed_hosts(values: list[str]) -> set[str]:
    if any(not v or any(c.isspace() or c in "/\\?#@,:*" for c in v) for v in values):
        raise click.ClickException("server.allowed_hosts must contain exact hostnames without ports")
    return {_normalize_host(v) for v in values}


def request_host(request: Request) -> str | None:
    """Return the normalized Host header name, or None when it is malformed."""
    headers = request.headers.getlist("host")
    if len(headers) != 1:
        return None
    authority = headers[0]
    if (
        not authority
        or authority.endswith(":")
        or any(c.isspace() or c in "/\\?#@," for c in authority)
    ):
        return None
    try:
        parsed = urlsplit(f"//{authority}")
        host_header = parsed.hostname
        # Accessing port validates its syntax and range.
        parsed.port
        if authority.startswith("["):
            suffix = authority.partition("]")[2]
            if suffix and not suffix.startswith(":"):
                return None
        elif authority.count(":") > 1:
            return None
    except ValueError:
        return None
    return _normalize_host(host_header) if host_header else None


def local_host(request: Request) -> bool:
    listen = _normalize_host(state(request).listen_host)
    return request_host(request) in {listen, "localhost", "127.0.0.1", "::1"}


def proxy_host(request: Request) -> bool:
    host = request_host(request)
    return host is not None and host in state(request).allowed_hosts


def _configured(key: str) -> bool:
    try:
        value, _ = config.resolve(key)
    except click.ClickException:
        return True
    return bool(value)


@router.get("/meta")
def meta(request: Request) -> dict:
    try:
        jira, _ = config.resolve("jira.browse_url")
    except click.ClickException:
        jira = None
    return {
        "reviewConfigured": _configured("review.command"),
        "queueConfigured": _configured("queue.command"),
        "statusConfigured": _configured("status.command"),
        "jiraBrowseUrl": jira if local_host(request) and isinstance(jira, str) and jira.strip() else None,
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
    if not body.url.startswith(("http://", "https://")):
        raise HTTPException(400, "url must start with http:// or https://")
    with state(request).lock:
        try:
            open_http_url(body.url)
        except click.ClickException as e:
            raise ActionFailed(str(e)) from e
    return {"message": "opened url"}


@router.get("/config")
def get_config(request: Request) -> dict:
    return {
        "path": str(config.config_path()),
        "settings": views.config_settings(redact=not local_host(request)),
    }


class ValueBody(BaseModel):
    value: str = ""


@router.put("/config/{key}")
def set_config(key: str, body: ValueBody, request: Request) -> dict:
    try:
        config.setting(key)
    except click.BadParameter as e:
        raise HTTPException(400, str(e)) from e
    try:
        message = state(request).save_setting(key, body.value)
    except views.SettingError as e:
        raise ActionFailed(str(e)) from e
    return {"message": message}


@router.delete("/config/{key}")
def unset_config(key: str, request: Request) -> dict:
    try:
        config.setting(key)
    except click.BadParameter as e:
        raise HTTPException(400, str(e)) from e
    try:
        message = state(request).save_setting(key, "", unset=True)
    except views.SettingError as e:
        raise ActionFailed(str(e)) from e
    return {"message": message}
