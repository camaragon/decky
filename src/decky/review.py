"""Template interpolation for review and browser commands."""

from __future__ import annotations

import re
from pathlib import Path


def interpolate(template: str, *, slug: str, number: int, dest: Path) -> str:
    owner, _, repo = slug.partition("/")
    mapping = {
        "slug": slug,
        "owner": owner,
        "repo": repo,
        "number": str(number),
        "url": f"https://github.com/{slug}/pull/{number}",
        "cwd": str(dest),
    }

    def repl(match: re.Match[str]) -> str:
        name = match.group(1)
        return mapping.get(name, match.group(0))

    return re.sub(r"\{([a-z]+)\}", repl, template)
