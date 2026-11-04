"""tmux window backend for PR review."""

from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path
from shutil import which

import click

from decky import config, review


def _parse_pr_url(url: str) -> tuple[str, int]:
    slug = url.split("/pull/")[0].split("github.com/")[-1]
    number = int(url.rsplit("/", 1)[-1])
    return slug, number


class TmuxBackend:
    def _binary(self) -> str:
        override, _ = config.resolve("tmux.bin")
        if override:
            return str(override)
        found = which("tmux")
        if not found:
            raise click.ClickException("tmux not found")
        return found

    def _session(self, binary: str) -> str:
        configured, _ = config.resolve("tmux.session")
        if configured:
            return str(configured)
        if os.environ.get("TMUX"):
            result = subprocess.run(
                [binary, "display-message", "-p", "#S"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        return "decky"

    def _run(self, binary: str, args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
        result = subprocess.run([binary, *args], capture_output=True, text=True, check=False)
        if check and result.returncode != 0:
            message = (result.stderr or result.stdout).strip()
            raise click.ClickException(f"tmux failed: {message}")
        return result

    def _window_names(self, binary: str, session: str) -> list[str]:
        result = self._run(binary, ["list-windows", "-t", session, "-F", "#{window_name}"], check=False)
        if result.returncode != 0:
            return []
        return [line for line in result.stdout.splitlines() if line]

    def _ensure_session(self, binary: str, session: str) -> None:
        has = subprocess.run([binary, "has-session", "-t", session], capture_output=True, check=False)
        if has.returncode != 0:
            self._run(binary, ["new-session", "-d", "-s", session])

    def _open_browser(self, url: str, dest: Path) -> None:
        slug, number = _parse_pr_url(url)
        template, _ = config.resolve("browser.command")
        template = template or "open {url}"
        cmd = review.interpolate(template, slug=slug, number=number, dest=dest)
        subprocess.run(shlex.split(cmd), check=False)

    def focus_existing(self, name: str, url: str) -> bool:
        binary = self._binary()
        session = self._session(binary)
        if name not in self._window_names(binary, session):
            return False
        self._run(binary, ["select-window", "-t", f"{session}:{name}"])
        self._open_browser(url, Path("."))
        return True

    def open(self, name: str, cwd: Path, command: str, url: str) -> None:
        binary = self._binary()
        session = self._session(binary)
        self._ensure_session(binary, session)
        self._run(
            binary,
            ["new-window", "-t", session, "-n", name, "-c", str(cwd), command],
        )
        self._open_browser(url, cwd)
        if not os.environ.get("TMUX"):
            click.echo(f"tmux attach -t {session}", err=True)
