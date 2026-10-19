"""Optional Presidio initialization, label mapping, and detection."""
from ..schemas import AnalyzeRequest, Entity

PRESIDIO_TYPE_MAP = {
    "PERSON": "person", "EMAIL_ADDRESS": "email", "PHONE_NUMBER": "phone",
    "CREDIT_CARD": "credit_card", "IP_ADDRESS": "ip_address", "LOCATION": "address",
    "IBAN_CODE": "iban", "US_SSN": "us_ssn", "US_PASSPORT": "passport",
}


def load_presidio():
    try:
        from presidio_analyzer import AnalyzerEngine
    except ImportError:
        return None
    try:
        return AnalyzerEngine()
    except Exception:
        # Preserve operation when the requested language model is unavailable.
        return None


class PresidioDetector:
    def __init__(self) -> None:
        self.analyzer = load_presidio()

    @property
    def available(self) -> bool:
        return self.analyzer is not None

    def analyze(self, request: AnalyzeRequest) -> list[Entity]:
        found: list[Entity] = []
        if self.analyzer is not None:
            try:
                for item in self.analyzer.analyze(text=request.text, language=request.language):
                    found.append(Entity(
                        type=PRESIDIO_TYPE_MAP.get(item.entity_type, item.entity_type.lower()),
                        start=item.start, end=item.end, score=item.score, source="presidio",
                    ))
            except Exception:
                # Preserve the existing fallback for unsupported languages.
                pass
        return found
