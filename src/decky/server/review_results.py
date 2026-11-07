"""Read optional local review results without following file symlinks."""

import os
import re
import stat
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

MAX_BYTES = 256 * 1024
Risk = Literal["low", "medium", "high"]


class Summary(BaseModel):
    model_config = ConfigDict(strict=True, str_strip_whitespace=True)
    what_changed: str = Field(min_length=1, max_length=10000)
    why: str = Field(min_length=1, max_length=10000)
    what_to_check: str = Field(min_length=1, max_length=10000)


class SecondOpinion(BaseModel):
    model_config = ConfigDict(strict=True, str_strip_whitespace=True)
    reviewer: str = Field(min_length=1, max_length=200)
    risk: Risk
    summary: str = Field(min_length=1, max_length=10000)


class ReviewResult(BaseModel):
    model_config = ConfigDict(strict=True, str_strip_whitespace=True)
    version: Literal[1]
    head_sha: str = Field(pattern=r"^[a-fA-F0-9]{40}$")
    risk: Risk
    summary: Summary
    reviewer: str = Field(min_length=1, max_length=200)
    generated_at: str
    second_opinion: SecondOpinion | None = None

    @field_validator("version", mode="before")
    @classmethod
    def version_number(cls, value):
        if type(value) is not int:
            raise ValueError("version must be an integer")
        return value

    @field_validator("generated_at")
    @classmethod
    def timestamp(cls, value: str) -> str:
        if datetime.fromisoformat(value.replace("Z", "+00:00")).utcoffset() is None:
            raise ValueError("generated_at needs a timezone")
        return value


def load(directory: str | None, repo: str, number: int, head_sha: str) -> dict | None:
    """Absent, invalid, oversized or unreadable results leave the inbox usable."""
    if not directory:
        return None
    if not re.fullmatch(r"[A-Za-z0-9-]+/[A-Za-z0-9._-]+", repo):
        return None
    if type(number) is not int or number <= 0:
        return None
    # '+' cannot occur in GitHub names, so flat filenames cannot collide.
    filename = f"{repo.lower().replace('/', '+')}-{number}.json"
    try:
        root = os.open(Path(directory).expanduser(), os.O_RDONLY | os.O_DIRECTORY)
        try:
            fd = os.open(filename, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=root)
            with os.fdopen(fd, "rb") as file:
                if not stat.S_ISREG(os.fstat(file.fileno()).st_mode):
                    return None
                raw = file.read(MAX_BYTES + 1)
        finally:
            os.close(root)
        if len(raw) > MAX_BYTES:
            return None
        result = ReviewResult.model_validate_json(raw)
    except (OSError, ValueError, ValidationError):
        return None
    return {**result.model_dump(), "outdated": result.head_sha.lower() != head_sha.lower()}
