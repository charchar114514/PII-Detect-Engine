"""Service configuration, resolved independently of the working directory."""
import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config.json"
OFFLINE_MODE = os.getenv("OFFLINE_MODE", "true").lower() == "true"


class DetectorConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    rules: bool
    presidio: bool
    gliner: bool


def load_config(path: Path = CONFIG_PATH) -> DetectorConfig:
    # Fail rather than silently enabling engines when configuration is invalid.
    return DetectorConfig.model_validate_json(path.read_text(encoding="utf-8-sig"))
