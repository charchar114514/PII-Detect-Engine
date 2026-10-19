"""Local PII patterns, context matching, and structural validators.

Validation checks format, not whether a document was actually issued.
"""
import re
from datetime import date

from ..schemas import AnalyzeRequest, Entity


def contextual_pattern(labels: str, value: str) -> re.Pattern[str]:
    """Capture only the value, including in JSON-style quoted fields."""
    return re.compile(
        rf"(?<![A-Za-z0-9_])(?:{labels})[\"']?[ \t]*"
        rf"(?:[:：=#][ \t]*)?[\"']?(?P<value>{value})(?![A-Za-z0-9])",
        re.IGNORECASE | re.ASCII,
    )


ID_LABELS = r"身份证(?:号码|号碼|编号|編號|号|號)?|身份證(?:號碼|号码|編號|编号|號|号)?|(?:Chinese[ _-]*)?ID[ _-]*card(?:[ _-]*(?:number|no\.?))?"
SSN_LABELS = r"SSN|social[ _-]*security(?:[ _-]*(?:number|no\.?))?"
PASSPORT_LABELS = r"passport(?:[ _-]*(?:number|no\.?))?|护照(?:号码|号碼|编号|編號|号|號)?|護照(?:號碼|号码|編號|编号|號|号)?"

RULES: list[tuple[str, re.Pattern[str], float]] = [
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), 0.99),
    ("phone", re.compile(r"(?<!\d)(?:\+?\d{1,3}[ .-]?)?(?:\(?\d{2,4}\)?[ .-]?)?\d{3,4}[ .-]\d{3,4}(?!\d)"), 0.80),
    ("credit_card", re.compile(r"(?<!\d)(?:\d[ -]*?){13,19}(?!\d)"), 0.75),
    ("ip_address", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), 0.95),
    ("credential", re.compile(r"(?i)(?:api[_ -]?key|password|secret|private[_ -]?key)\s*[:=]\s*[^\s,;]+"), 0.99),
    # Mainland mobile numbers, including compact forms missed by the generic rule.
    ("phone", re.compile(r"(?<![A-Za-z0-9])(?:\+?86[ -]?)?1[3-9][0-9]{9}(?![A-Za-z0-9])"), 0.90),
    ("us_ssn", re.compile(r"(?<![A-Za-z0-9])[0-9]{3}(?P<separator>[- ])[0-9]{2}(?P=separator)[0-9]{4}(?![A-Za-z0-9])"), 0.95),
    # Compact SSNs require context to avoid treating arbitrary nine-digit IDs as SSNs.
    ("us_ssn", contextual_pattern(SSN_LABELS, r"[0-9]{9}"), 0.95),
    ("identity_number", re.compile(r"(?<![A-Za-z0-9])[1-9][0-9]{5}(?:18|19|20)[0-9]{2}[01][0-9][0-3][0-9][0-9]{3}[0-9Xx](?![A-Za-z0-9])"), 0.99),
    # Old 15-digit IDs have no check digit and need explicit document context.
    ("identity_number", contextual_pattern(ID_LABELS, r"[1-9][0-9]{14}"), 0.90),
    # Mainland ordinary passports: legacy G / E + 8 digits, or E + letter + 7 digits.
    ("passport", re.compile(r"(?<![A-Za-z0-9])(?:[GE][0-9]{8}|E[A-HJ-NP-Z][0-9]{7})(?![A-Za-z0-9])", re.IGNORECASE | re.ASCII), 0.90),
    # Other countries vary; this deliberately checks only a context-bound candidate.
    ("passport", contextual_pattern(PASSPORT_LABELS, r"[A-Z0-9]{6,9}"), 0.80),
]


def valid_ssn(value: str) -> bool:
    digits = value.replace("-", "").replace(" ", "")
    return (
        digits[:3] not in {"000", "666"}
        and int(digits[:3]) < 900
        and digits[3:5] != "00"
        and digits[5:] != "0000"
    )


def valid_chinese_id(value: str) -> bool:
    # Province-level prefixes only: no claim to verify historical county codes.
    provinces = {
        "11", "12", "13", "14", "15", "21", "22", "23", "31", "32", "33",
        "34", "35", "36", "37", "41", "42", "43", "44", "45", "46", "50",
        "51", "52", "53", "54", "61", "62", "63", "64", "65", "71", "81", "82",
    }
    if value[:2] not in provinces or value[2:6] == "0000":
        return False
    birthday = value[6:14] if len(value) == 18 else "19" + value[6:12]
    sequence = value[14:17] if len(value) == 18 else value[12:15]
    try:
        born = date(int(birthday[:4]), int(birthday[4:6]), int(birthday[6:8]))
    except ValueError:
        return False
    if born > date.today() or sequence == "000":
        return False
    if len(value) == 15:
        return True
    weights = (7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2)
    checksum = sum(int(digit) * weight for digit, weight in zip(value[:17], weights))
    return value[-1].upper() == "10X98765432"[checksum % 11]


def valid_candidate(kind: str, value: str) -> bool:
    if kind == "us_ssn":
        return valid_ssn(value)
    if kind == "identity_number":
        return valid_chinese_id(value)
    if kind == "passport":
        return any(character.isdigit() for character in value)
    return True


class RulesDetector:
    available = True

    def analyze(self, request: AnalyzeRequest) -> list[Entity]:
        found: dict[tuple[str, int, int], Entity] = {}
        for kind, pattern, score in RULES:
            for match in pattern.finditer(request.text):
                group = "value" if "value" in match.re.groupindex else 0
                start, end = match.span(group)
                if not valid_candidate(kind, request.text[start:end]):
                    continue
                entity = Entity(type=kind, start=start, end=end, score=score, source="rule")
                key = (kind, start, end)
                if key not in found or score > found[key].score:
                    found[key] = entity

        # Generic digit patterns must not override a recognized identity document.
        identifiers = [e for e in found.values() if e.type in {"identity_number", "us_ssn", "passport"}]
        return [
            entity for entity in found.values()
            if entity.type not in {"phone", "credit_card"} or not any(
                entity.start < identifier.end and identifier.start < entity.end
                for identifier in identifiers
            )
        ]
