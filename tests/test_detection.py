import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from pii_engine.config import DetectorConfig
from pii_engine.detector import Detector
from pii_engine.engines import gliner, presidio
from pii_engine.engines.rules import RulesDetector
from pii_engine.schemas import AnalyzeRequest


class DetectionTests(unittest.TestCase):
    def test_rules_preserve_types_scores_and_exact_spans(self):
        cases = [
            ("email", "alice@example.com", 0.99),
            ("phone", "555-1234", 0.80),
            ("credit_card", "4111111111111111", 0.75),
            ("ip_address", "192.168.1.1", 0.95),
            ("credential", "password=example", 0.99),
        ]
        for kind, value, score in cases:
            with self.subTest(kind=kind):
                text = f"Before {value} after"
                entities = RulesDetector().analyze(AnalyzeRequest(text=text))
                matches = [entity for entity in entities if entity.type == kind]
                self.assertEqual(len(matches), 1)
                self.assertEqual(matches[0].score, score)
                self.assertEqual(matches[0].source, "rule")
                self.assertEqual(text[matches[0].start:matches[0].end], value)

    def test_merge_preserves_highest_score_and_position_order(self):
        analyzer = Mock()
        analyzer.analyze.return_value = [
            SimpleNamespace(entity_type="EMAIL_ADDRESS", start=6, end=23, score=0.8),
            SimpleNamespace(entity_type="PERSON", start=0, end=5, score=0.9),
        ]
        model = Mock()
        model.extract_entities.return_value = {
            "entities": {"email": [{"start": 6, "end": 23, "confidence": 0.995}]}
        }
        with patch.object(presidio, "load_presidio", return_value=analyzer), \
             patch.object(gliner, "load_gliner", return_value=model):
            detector = Detector(DetectorConfig(rules=True, presidio=True, gliner=True))
        result = detector.analyze(AnalyzeRequest(text="Alice alice@example.com"))
        self.assertEqual([(e.type, e.start, e.end) for e in result.entities],
                         [("person", 0, 5), ("email", 6, 23)])
        self.assertEqual(result.entities[1].source, "gliner")
        self.assertEqual(result.entities[1].score, 0.995)

    def test_presidio_failure_preserves_other_engine_results(self):
        analyzer = Mock()
        analyzer.analyze.side_effect = RuntimeError("Language unavailable")
        with patch.object(presidio, "load_presidio", return_value=analyzer):
            detector = Detector(DetectorConfig(rules=True, presidio=True, gliner=False))
        result = detector.analyze(AnalyzeRequest(text="alice@example.com"))
        self.assertEqual([e.source for e in result.entities], ["rule"])

    def test_gliner_span_parsing_and_score_fallback(self):
        model = Mock()
        model.extract_entities.return_value = {"entities": {"person": [
            "Alice", {"start": "0", "end": 5},
            {"start": 0, "end": 5, "score": 0.8},
        ]}}
        with patch.object(gliner, "load_gliner", return_value=model):
            engine = gliner.GlinerDetector()
        entities = engine.analyze(AnalyzeRequest(text="Alice"))
        self.assertEqual(len(entities), 1)
        self.assertEqual(entities[0].score, 0.8)
        self.assertEqual(entities[0].source, "gliner")

    def test_presidio_ssn_uses_same_type_as_rules(self):
        analyzer = Mock()
        analyzer.analyze.return_value = [
            SimpleNamespace(entity_type="US_SSN", start=0, end=11, score=0.7)
        ]
        with patch.object(presidio, "load_presidio", return_value=analyzer):
            detector = Detector(DetectorConfig(rules=True, presidio=True, gliner=False))
        entities = detector.analyze(AnalyzeRequest(text="219-09-9999")).entities
        self.assertEqual(len(entities), 1)
        self.assertEqual(entities[0].type, "us_ssn")
        self.assertEqual(entities[0].source, "rule")


if __name__ == "__main__":
    unittest.main()
