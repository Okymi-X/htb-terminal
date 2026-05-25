from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


DEFAULT_BASE_URL = "https://labs.hackthebox.com/api/v4"


@dataclass(frozen=True)
class Config:
    base_url: str
    token: str


class ConfigError(RuntimeError):
    pass


def load_token(token_file: Path | None = None) -> str:
    env_token = os.environ.get("HTB_API_TOKEN")
    if env_token:
        return _normalize_token(env_token)

    path = token_file or Path("api.token")
    if not path.exists():
        raise ConfigError(
            f"Token missing. Put it in {path} or export HTB_API_TOKEN."
        )

    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        raise ConfigError(f"Token file is empty: {path}")

    return _normalize_token(raw)


def load_config(token_file: Path | None = None, base_url: str | None = None) -> Config:
    return Config(
        base_url=(base_url or os.environ.get("HTB_API_BASE_URL") or DEFAULT_BASE_URL).rstrip("/"),
        token=load_token(token_file),
    )


def _normalize_token(value: str) -> str:
    token = value.strip()
    if not token:
        raise ConfigError("Empty API token.")

    if token.lower().startswith("authorization:"):
        token = token.split(":", 1)[1].strip()

    if token.lower().startswith("bearer "):
        token = token.split(None, 1)[1].strip()

    return token

