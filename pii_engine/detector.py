"""Configure detection engines and merge their results."""
from .config import OFFLINE_MODE, DetectorConfig
from .engines.gliner import GlinerDetector
from .engines.presidio import PresidioDetector
from .engines.rules import RulesDetector
from .schemas import AnalyzeRequest, AnalyzeResponse, Entity


class Detector:
    def __init__(self, config: DetectorConfig) -> None:
        self.config = config
        self.rules = RulesDetector() if config.rules else None
        self.presidio = PresidioDetector() if config.presidio else None
        self.gliner = GlinerDetector() if config.gliner else None

    def engine_status(self) -> dict[str, bool]:
        return {
            "rules": self.rules is not None and self.rules.available,
            "presidio": self.presidio is not None and self.presidio.available,
            "gliner": self.gliner is not None and self.gliner.available,
            "offline_mode": OFFLINE_MODE,
        }

    def analyze(self, request: AnalyzeRequest) -> AnalyzeResponse:
        found: list[Entity] = []
        for engine in (self.rules, self.presidio, self.gliner):
            if engine is not None:
                found.extend(engine.analyze(request))

        # Exact span/type dedupe; preserve the highest score.
        unique: dict[tuple[str, int, int], Entity] = {}
        for item in found:
            key = (item.type, item.start, item.end)
            if key not in unique or item.score > unique[key].score:
                unique[key] = item
        return AnalyzeResponse(
            entities=sorted(unique.values(), key=lambda item: (item.start, item.end)),
            engine=self.engine_status(),
        )
