"""Service configuration, resolved independently of the working directory."""
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

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


class PresidioConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    models: dict[Literal["en", "zh"], str] = Field(min_length=1)


def load_presidio_config(path: Path = PROJECT_ROOT / "presidio-config.json") -> PresidioConfig:
    return PresidioConfig.model_validate_json(path.read_text(encoding="utf-8-sig"))
