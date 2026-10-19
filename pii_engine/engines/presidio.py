"""Optional bilingual Presidio initialization, label mapping, and detection."""
import logging

from ..config import load_presidio_config
from ..schemas import AnalyzeRequest, Entity

logger = logging.getLogger(__name__)

PRESIDIO_TYPE_MAP = {
    "PERSON": "person", "EMAIL_ADDRESS": "email", "PHONE_NUMBER": "phone",
    "CREDIT_CARD": "credit_card", "IP_ADDRESS": "ip_address", "LOCATION": "address",
    "IBAN_CODE": "iban", "US_SSN": "us_ssn", "US_PASSPORT": "passport",
}


def load_presidio():
    config = load_presidio_config()
    try:
        from presidio_analyzer import AnalyzerEngine
        from presidio_analyzer.nlp_engine import NlpEngineProvider
        from spacy.util import is_package
    except ImportError:
        logger.warning("Presidio dependencies are unavailable")
        return None

    # Preflight installed packages: spaCy/Presidio must not download at startup.
    models = []
    for language, model in config.models.items():
        if is_package(model):
            models.append({"lang_code": language, "model_name": model})
        else:
            logger.warning("Presidio model %s for %s is not installed; language disabled", model, language)
    if not models:
        return None
    try:
        nlp_engine = NlpEngineProvider(nlp_configuration={
            "nlp_engine_name": "spacy", "models": models,
            # Preserve the previous default English entity mapping and exclusions.
            "ner_model_configuration": {
                "model_to_presidio_entity_mapping": {
                    "PER": "PERSON", "PERSON": "PERSON", "NORP": "NRP",
                    "FAC": "LOCATION", "LOC": "LOCATION", "GPE": "LOCATION",
                    "LOCATION": "LOCATION", "ORG": "ORGANIZATION",
                    "ORGANIZATION": "ORGANIZATION", "DATE": "DATE_TIME", "TIME": "DATE_TIME",
                },
                "labels_to_ignore": [
                    "ORGANIZATION", "CARDINAL", "EVENT", "LANGUAGE", "LAW", "MONEY",
                    "ORDINAL", "PERCENT", "PRODUCT", "QUANTITY", "WORK_OF_ART",
                ],
            },
        }).create_engine()
        analyzer = AnalyzerEngine(
            nlp_engine=nlp_engine,
            supported_languages=[model["lang_code"] for model in models],
        )
        if "zh" in analyzer.supported_languages:
            register_chinese_recognizers(analyzer.registry)
        return analyzer
    except Exception:
        logger.exception("Presidio initialization failed")
        return None


def register_chinese_recognizers(registry) -> None:
    from presidio_analyzer.predefined_recognizers import (
        CreditCardRecognizer, CryptoRecognizer, EmailRecognizer, IbanRecognizer,
        IpRecognizer, MacAddressRecognizer, PhoneRecognizer, UrlRecognizer,
    )

    # Keep English defaults and add zh instances with Chinese context words.
    recognizers = [
        EmailRecognizer(supported_language="zh", context=["邮箱", "郵箱", "邮件", "電郵", "email"]),
        PhoneRecognizer(supported_language="zh", supported_regions=["CN", "HK", "TW"],
                        context=["电话", "電話", "手机", "手機", "聯絡", "联系"]),
        CreditCardRecognizer(supported_language="zh", context=["银行卡", "銀行卡", "信用卡", "卡号", "卡號"]),
        IbanRecognizer(supported_language="zh", context=["国际银行账号", "國際銀行帳號", "iban"]),
        IpRecognizer(supported_language="zh", context=["ip", "地址", "网络", "網絡"]),
        MacAddressRecognizer(supported_language="zh", context=["mac", "网卡", "網卡"]),
        UrlRecognizer(supported_language="zh", context=["网址", "網址", "链接", "連結"]),
        CryptoRecognizer(supported_language="zh", context=["比特币", "比特幣", "钱包", "錢包"]),
    ]
    for recognizer in recognizers:
        registry.add_recognizer(recognizer)


class PresidioDetector:
    def __init__(self) -> None:
        self.analyzer = load_presidio()

    @property
    def available(self) -> bool:
        return self.analyzer is not None

    @property
    def languages(self) -> list[str]:
        return list(self.analyzer.supported_languages) if self.analyzer is not None else []

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
                logger.exception("Presidio detection failed for language %s", request.language)
        return found
