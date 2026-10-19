"""Shared HTTP and detector data structures."""
from typing import Literal

from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    text: str = Field(min_length=1, max_length=50_000)
    language: str = Field(default="en", min_length=2, max_length=8)
    include_ner: bool = True


class Entity(BaseModel):
    type: str
    start: int
    end: int
    score: float
    source: Literal["rule", "presidio", "gliner"]


class AnalyzeResponse(BaseModel):
    entities: list[Entity]
    engine: dict[str, bool]
