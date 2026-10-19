"""Bilingual Presidio and Unicode regression coverage, without GLiNER2 loading."""
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import app
from pii_engine.config import DetectorConfig, PresidioConfig, load_presidio_config
from pii_engine.engines.presidio import load_presidio


class ChineseConfigTests(unittest.TestCase):
    def test_bilingual_models_are_configured(self):
        self.assertEqual(set(load_presidio_config().models), {"en", "zh"})

    def test_missing_models_do_not_trigger_downloads(self):
        with patch("spacy.util.is_package", return_value=False), \
             patch("presidio_analyzer.nlp_engine.NlpEngineProvider.create_engine") as create:
            self.assertIsNone(load_presidio())
            create.assert_not_called()

    def test_invalid_language_is_rejected(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            PresidioConfig(models={"invalid": "model"})


class ChinesePresidioIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from spacy.util import is_package
        if not all(is_package(model) for model in load_presidio_config().models.values()):
            raise unittest.SkipTest("Install configured spaCy models to run bilingual model tests")
        cls.analyzer = load_presidio()
        if cls.analyzer is None:
            raise AssertionError("Bilingual Presidio initialization failed")

    def test_chinese_ner_and_english_remain_available(self):
        self.assertEqual(set(self.analyzer.supported_languages), {"en", "zh"})
        chinese = self.analyzer.analyze(text="张三在北京工作。", language="zh")
        self.assertTrue(any(entity.entity_type == "PERSON" for entity in chinese))
        self.assertTrue(any(entity.entity_type == "LOCATION" for entity in chinese))
        english = self.analyzer.analyze(text="Email alice@example.com", language="en")
        self.assertTrue(any(entity.entity_type == "EMAIL_ADDRESS" for entity in english))

    def test_zh_recognizers_are_registered(self):
        types = set(self.analyzer.get_supported_entities(language="zh"))
        self.assertTrue({"PERSON", "LOCATION", "EMAIL_ADDRESS", "PHONE_NUMBER", "CREDIT_CARD",
                         "IBAN_CODE", "IP_ADDRESS", "MAC_ADDRESS", "URL", "CRYPTO"} <= types)
        self.assertNotIn("ORGANIZATION", types)

    def test_chinese_and_traditional_context_with_exact_unicode_offsets(self):
        for text in ("😀𠀀 联系邮箱 alice@example.com", "😀 聯絡電郵 alice@example.com"):
            with self.subTest(text=text):
                entities = self.analyzer.analyze(text=text, language="zh", entities=["EMAIL_ADDRESS"])
                self.assertTrue(entities)
                self.assertEqual(text[entities[0].start:entities[0].end], "alice@example.com")

    def test_bilingual_http_health_and_rules(self):
        with patch.object(app, "load_config", return_value=DetectorConfig(
            rules=True, presidio=True, gliner=False,
        )), patch("pii_engine.engines.presidio.load_presidio", return_value=self.analyzer), \
             TestClient(app.app) as client:
            self.assertEqual(set(client.get("/health").json()["presidio_languages"]), {"en", "zh"})
            text = "😀张三在北京，身份证11010519491231002X，邮箱alice@example.com"
            result = client.post("/analyze", json={"text": text, "language": "zh"})
            self.assertEqual(result.status_code, 200)
            entities = result.json()["entities"]
            self.assertTrue(any(e["type"] == "identity_number" for e in entities))
            self.assertTrue(any(e["type"] == "email" for e in entities))
            for entity in entities:
                self.assertTrue(text[entity["start"]:entity["end"]])


if __name__ == "__main__":
    unittest.main()
