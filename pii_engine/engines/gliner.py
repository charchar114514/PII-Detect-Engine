"""Optional local GLiNER2 loading, PII labels, and span extraction."""
import os

from ..config import PROJECT_ROOT
from ..schemas import AnalyzeRequest, Entity

GLINER_MODEL_PATH = os.getenv(
    "GLINER_MODEL_PATH", str(PROJECT_ROOT / "models" / "fastino-gliner2-privacy-filter-PII-multi")
)
GLINER_THRESHOLD = float(os.getenv("GLINER_THRESHOLD", "0.65"))
ENTITY_LABELS = [
    "person", "full_name", "email", "phone_number", "address", "street_address",
    "date_of_birth", "government_id", "national_id_number", "passport_number",
    "drivers_license_number", "tax_id", "bank_account", "account_number",
    "routing_number", "iban", "payment_card", "card_number", "card_expiry",
    "card_cvv", "username", "ip_address", "account_id", "sensitive_account_id",
    "password", "secret", "api_key", "access_token", "recovery_code",
]


def load_gliner():
    try:
        from gliner2 import GLiNER2
    except ImportError:
        return None
    if os.path.isdir(GLINER_MODEL_PATH):
        return GLiNER2.from_pretrained(GLINER_MODEL_PATH)
    return None


class GlinerDetector:
    def __init__(self) -> None:
        self.model = load_gliner()

    @property
    def available(self) -> bool:
        return self.model is not None

    def analyze(self, request: AnalyzeRequest) -> list[Entity]:
        if not request.include_ner or self.model is None:
            return []
        result = self.model.extract_entities(
            request.text, ENTITY_LABELS, threshold=GLINER_THRESHOLD,
            include_confidence=True, include_spans=True,
        )
        found: list[Entity] = []
        for label, values in result.get("entities", {}).items():
            for item in values:
                if not isinstance(item, dict):
                    continue
                start, end = item.get("start"), item.get("end")
                if isinstance(start, int) and isinstance(end, int):
                    found.append(Entity(
                        type=label, start=start, end=end,
                        score=float(item.get("confidence", item.get("score", 0.0))), source="gliner",
                    ))
        return found
