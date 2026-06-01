"""Config + environment loading. Single place that reads YAML and .env."""

from __future__ import annotations

import os
from pathlib import Path
from functools import lru_cache

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dependency is in requirements.txt

    def load_dotenv(*_args, **_kwargs) -> None:
        return None


ROOT = Path(__file__).resolve().parents[2]
CONFIGS = ROOT / "configs"
DATA = ROOT / "data"

load_dotenv(ROOT / ".env")


@lru_cache(maxsize=None)
def load_yaml(name: str) -> dict:
    """Load a YAML config from configs/ by filename (with or without .yaml)."""
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - environment setup issue
        raise RuntimeError(
            "Missing PyYAML. Install project dependencies with "
            "`pip install -r requirements.txt`."
        ) from exc

    if not name.endswith((".yaml", ".yml")):
        name += ".yaml"
    with open(CONFIGS / name, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def env(key: str, required: bool = True) -> str | None:
    """Read a secret from the environment (.env)."""
    val = os.getenv(key)
    if required and not val:
        raise RuntimeError(f"Missing {key}. Copy .env.example to .env and fill it in.")
    return val


def weights() -> dict:
    return load_yaml("weights")


def fred_series() -> dict:
    return load_yaml("fred_series")
