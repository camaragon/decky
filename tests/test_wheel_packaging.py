"""Wheel install smoke: built SPA is on disk and GET / returns 200."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from decky.server.app import STATIC, create_app

pytestmark = pytest.mark.skipif(
    not (STATIC / "index.html").is_file(),
    reason="requires built SPA (hatch build / pnpm -C web build)",
)


def test_wheel_includes_spa() -> None:
    assert (STATIC / "index.html").is_file()


def test_root_returns_200() -> None:
    with TestClient(create_app(host="127.0.0.1"), base_url="http://127.0.0.1") as client:
        assert client.get("/").status_code == 200
