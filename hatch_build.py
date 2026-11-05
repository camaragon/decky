"""Hatch build hook: run pnpm build so the wheel ships the SPA."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):
    PLUGIN_NAME = "custom"

    def initialize(self, version: str, build_data: dict) -> None:
        root = Path(self.root)
        web = root / "web"
        if not (web / "package.json").is_file():
            return
        if not (web / "pnpm-lock.yaml").is_file():
            raise OSError("web/pnpm-lock.yaml is required to build the SPA")

        subprocess.run(["corepack", "enable"], cwd=root, check=True)

        node_modules = web / "node_modules"
        if node_modules.exists():
            shutil.rmtree(node_modules)

        subprocess.run(["pnpm", "install", "--frozen-lockfile"], cwd=web, check=True)
        if not (web / "node_modules" / "react").is_dir():
            raise OSError("pnpm install did not populate web/node_modules")

        subprocess.run(["pnpm", "run", "build"], cwd=web, check=True)
        index = root / "src" / "decky" / "server" / "static" / "index.html"
        if not index.is_file():
            raise OSError("web build did not produce src/decky/server/static/index.html")
