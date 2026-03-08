import tomllib
from pathlib import Path

DEFAULT_CONFIG = {
    "sync_start": "2019-01-01",
    "calendars": [],
    "babel_analysis": True,
}


def load_config(path=None):
    if path is None:
        path = Path.home() / ".config" / "calsync" / "config.toml"
    path = Path(path)
    if not path.exists():
        return DEFAULT_CONFIG

    with open(path, "rb") as f:
        config = tomllib.load(f)

    return {**DEFAULT_CONFIG, **config}
