"""HTTP entry point for the local PII detection service."""
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI

from pii_engine.config import load_config
from pii_engine.detector import Detector
from pii_engine.schemas import AnalyzeRequest, AnalyzeResponse

# GLiNER2 logs Unicode during initialization; Windows may otherwise use GBK.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

detector: Detector


@asynccontextmanager
async def lifespan(_: FastAPI):
    global detector
    detector = Detector(load_config())
    yield


app = FastAPI(title="PII Detect Engine", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, object]:
    return {
        "status": "ok", **detector.engine_status(), "configured": detector.config.model_dump(),
        "presidio_languages": detector.presidio.languages if detector.presidio else [],
    }


@app.post("/analyze", response_model=AnalyzeResponse)
def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    return detector.analyze(request)
