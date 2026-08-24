"""Offline-first PII detection HTTP service for AI Bridge.

Rules are always local. Presidio enriches standard PII recognition when installed.
GLiNER is optional and is loaded only from a local model directory; it never downloads
models while OFFLINE_MODE=true.
"""
from __future__ import annotations

import os
import re
import sys
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel, Field

# GLiNER2 logs Unicode symbols during model initialization. Windows PowerShell
# can default to GBK; force UTF-8 so logging never prevents offline startup.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

try:
    from presidio_analyzer import AnalyzerEngine
except ImportError:  # Useful during minimal development installs.
    AnalyzerEngine = None

try:
    from gliner2 import GLiNER2
except ImportError:
    GLiNER2 = None


OFFLINE_MODE = os.getenv("OFFLINE_MODE", "true").lower() == "true"
GLINER_MODEL_PATH = os.getenv("GLINER_MODEL_PATH", "./models/fastino-gliner2-privacy-filter-PII-multi")
GLINER_THRESHOLD = float(os.getenv("GLINER_THRESHOLD", "0.65"))
ENTITY_LABELS = [
    "person", "full_name", "email", "phone_number", "address", "street_address",
    "date_of_birth", "government_id", "national_id_number", "passport_number",
    "drivers_license_number", "tax_id", "bank_account", "account_number",
    "routing_number", "iban", "payment_card", "card_number", "card_expiry",
    "card_cvv", "username", "ip_address", "account_id", "sensitive_account_id",
    "password", "secret", "api_key", "access_token", "recovery_code",
]

RULES: list[tuple[str, re.Pattern[str], float]] = [
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), 0.99),
    ("phone", re.compile(r"(?<!\d)(?:\+?\d{1,3}[ .-]?)?(?:\(?\d{2,4}\)?[ .-]?)?\d{3,4}[ .-]\d{3,4}(?!\d)"), 0.80),
    ("credit_card", re.compile(r"(?<!\d)(?:\d[ -]*?){13,19}(?!\d)"), 0.75),
    ("ip_address", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), 0.95),
    ("credential", re.compile(r"(?i)(?:api[_ -]?key|password|secret|private[_ -]?key)\s*[:=]\s*[^\s,;]+"), 0.99),
]

PRESIDIO_TYPE_MAP = {
    "PERSON": "person", "EMAIL_ADDRESS": "email", "PHONE_NUMBER": "phone",
    "CREDIT_CARD": "credit_card", "IP_ADDRESS": "ip_address", "LOCATION": "address",
    "IBAN_CODE": "iban", "US_SSN": "identity_number", "US_PASSPORT": "passport",
}


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


class Detector:
    def __init__(self) -> None:
        self.analyzer = None
        # Presidio's default engine may attempt to download a spaCy model on first
        # startup. A missing model must never prevent the deterministic offline
        # protection layer from serving requests.
        if AnalyzerEngine:
            try:
                self.analyzer = AnalyzerEngine()
            except Exception:
                self.analyzer = None
        self.gliner = None
        # A missing local model is not an error: the deterministic layer still protects data.
        if GLiNER2 and os.path.isdir(GLINER_MODEL_PATH):
            # The model was downloaded explicitly into this directory. No hub
            # identifier is passed here, preventing any inference-time download.
            self.gliner = GLiNER2.from_pretrained(GLINER_MODEL_PATH)

    def analyze(self, request: AnalyzeRequest) -> AnalyzeResponse:
        found: list[Entity] = []
        for kind, pattern, score in RULES:
            found.extend(Entity(type=kind, start=m.start(), end=m.end(), score=score, source="rule") for m in pattern.finditer(request.text))

        if self.analyzer:
            try:
                for item in self.analyzer.analyze(text=request.text, language=request.language):
                    found.append(Entity(type=PRESIDIO_TYPE_MAP.get(item.entity_type, item.entity_type.lower()), start=item.start, end=item.end, score=item.score, source="presidio"))
            except Exception:
                # A language model may not be installed for every requested language.
                pass

        if request.include_ner and self.gliner:
            result = self.gliner.extract_entities(
                request.text, ENTITY_LABELS, threshold=GLINER_THRESHOLD,
                include_confidence=True, include_spans=True,
            )
            for label, values in result.get("entities", {}).items():
                for item in values:
                    if not isinstance(item, dict):
                        continue
                    start, end = item.get("start"), item.get("end")
                    if isinstance(start, int) and isinstance(end, int):
                        found.append(Entity(type=label, start=start, end=end, score=float(item.get("confidence", item.get("score", 0.0))), source="gliner"))

        # Exact span/type dedupe; preserve the most reliable source/score.
        unique: dict[tuple[str, int, int], Entity] = {}
        for item in found:
            key = (item.type, item.start, item.end)
            if key not in unique or item.score > unique[key].score:
                unique[key] = item
        return AnalyzeResponse(entities=sorted(unique.values(), key=lambda x: (x.start, x.end)), engine={"presidio": self.analyzer is not None, "gliner": self.gliner is not None, "offline_mode": OFFLINE_MODE})


detector: Detector

@asynccontextmanager
async def lifespan(_: FastAPI):
    global detector
    detector = Detector()
    yield


app = FastAPI(title="PII Detect Engine", version="0.1.0", lifespan=lifespan)

@app.get("/health")
def health() -> dict[str, object]:
    return {"status": "ok", "offline_mode": OFFLINE_MODE, "presidio": detector.analyzer is not None, "gliner": detector.gliner is not None}

@app.post("/analyze", response_model=AnalyzeResponse)
def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    return detector.analyze(request)
