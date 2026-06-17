from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_BASE_URL = "https://labs.hackthebox.com/api/v4"


@dataclass(frozen=True)
class Config:
    base_url: str
    token: str


class ConfigError(RuntimeError):
    pass


def user_config_dir() -> Path:
    """Per-user config directory, following the XDG base-directory spec."""
    override = os.environ.get("XDG_CONFIG_HOME")
    base = Path(override) if override else Path.home() / ".config"
    return base / "htb-terminal"


def user_token_path() -> Path:
    """Where ``htb init`` saves the token for a global (pipx) install."""
    return user_config_dir() / "token"


def save_token(token: str, token_file: Path | None = None) -> Path:
    """Normalize and persist a token, returning where it was written.

    Defaults to the user config file so a pipx-installed ``htb`` finds it from
    any directory. The file is created with owner-only permissions.
    """
    normalized = _normalize_token(token)
    path = token_file or user_token_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(normalized + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path


def _resolve_token_path(token_file: Path | None) -> Path | None:
    if token_file is not None:
        return token_file
    local = Path("api.token")
    if local.exists():
        return local
    user = user_token_path()
    if user.exists():
        return user
    return None


def load_token(token_file: Path | None = None) -> str:
    env_token = os.environ.get("HTB_API_TOKEN")
    if env_token:
        return _normalize_token(env_token)

    path = _resolve_token_path(token_file)
    if path is None or not path.exists():
        target = f" ({path})" if path is not None else ""
        raise ConfigError(
            f"Token missing{target}. Run 'htb init' to save one, "
            "put it in ./api.token, or export HTB_API_TOKEN."
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

