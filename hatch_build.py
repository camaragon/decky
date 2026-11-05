"""Hatch build hook: run pnpm build so the wheel ships the SPA."""

from __future__ import annotations

import subprocess
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):
    PLUGIN_NAME = "custom"

    def initialize(self, version: str, build_data: dict) -> None:
        root = Path(self.root)
        if not (root / "web" / "package.json").is_file():
            return
        subprocess.run(["corepack", "enable"], cwd=root, check=True)
        subprocess.run(["pnpm", "-C", "web", "install", "--frozen-lockfile"], cwd=root, check=True)
        subprocess.run(["pnpm", "-C", "web", "build"], cwd=root, check=True)
        index = root / "src" / "decky" / "server" / "static" / "index.html"
        if not index.is_file():
            raise OSError("web build did not produce src/decky/server/static/index.html")
