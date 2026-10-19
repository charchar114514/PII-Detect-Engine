import itertools
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from pydantic import ValidationError

import app
from pii_engine import config as settings
from pii_engine.detector import Detector
from pii_engine.engines import gliner as gliner_engine, presidio as presidio_engine
from pii_engine.schemas import AnalyzeRequest


class EngineConfigTests(unittest.TestCase):
    def test_all_engine_combinations(self):
        """Only enabled engines load and contribute entities, including rules-only."""
        for rules, presidio, gliner in itertools.product((False, True), repeat=3):
            with self.subTest(rules=rules, presidio=presidio, gliner=gliner):
                analyzer = Mock()
                analyzer.analyze.return_value = [
                    SimpleNamespace(entity_type="PERSON", start=0, end=5, score=0.9)
                ]
                model = Mock()
                model.extract_entities.return_value = {
                    "entities": {"full_name": [{"start": 0, "end": 5, "confidence": 0.9}]}
                }
                config = settings.DetectorConfig(rules=rules, presidio=presidio, gliner=gliner)
                with patch.object(presidio_engine, "load_presidio", return_value=analyzer) as load_p, \
                     patch.object(gliner_engine, "load_gliner", return_value=model) as load_g:
                    detector = Detector(config)
                    result = detector.analyze(AnalyzeRequest(text="Alice alice@example.com"))
                self.assertEqual(load_p.call_count, int(presidio))
                self.assertEqual(load_g.call_count, int(gliner))
                self.assertEqual(analyzer.analyze.call_count, int(presidio))
                self.assertEqual(model.extract_entities.call_count, int(gliner))
                expected_sources = {name for name, enabled in (
                    ("rule", rules), ("presidio", presidio), ("gliner", gliner)
                ) if enabled}
                self.assertEqual({entity.source for entity in result.entities}, expected_sources)
                self.assertEqual(result.engine["rules"], rules)
                self.assertEqual(result.engine["presidio"], presidio)
                self.assertEqual(result.engine["gliner"], gliner)

    def test_request_can_skip_gliner_without_skipping_other_engines(self):
        analyzer = Mock()
        analyzer.analyze.return_value = []
        model = Mock()
        config = settings.DetectorConfig(rules=True, presidio=True, gliner=True)
        with patch.object(presidio_engine, "load_presidio", return_value=analyzer), \
             patch.object(gliner_engine, "load_gliner", return_value=model):
            detector = Detector(config)
        result = detector.analyze(AnalyzeRequest(text="alice@example.com", include_ner=False))
        model.extract_entities.assert_not_called()
        analyzer.analyze.assert_called_once()
        self.assertTrue(any(entity.source == "rule" for entity in result.entities))
        self.assertTrue(result.engine["gliner"])  # Loaded, but skipped for this request.

    def test_enabled_but_unavailable_engines_report_unavailable(self):
        config = settings.DetectorConfig(rules=True, presidio=True, gliner=True)
        with patch.object(presidio_engine, "load_presidio", return_value=None), \
             patch.object(gliner_engine, "load_gliner", return_value=None):
            detector = Detector(config)
        self.assertFalse(detector.engine_status()["presidio"])
        self.assertFalse(detector.engine_status()["gliner"])
        self.assertTrue(detector.analyze(AnalyzeRequest(text="alice@example.com")).entities)

    def test_configuration_file_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            valid = {"rules": True, "presidio": False, "gliner": False}
            path.write_text(json.dumps(valid), encoding="utf-8-sig")
            self.assertEqual(settings.load_config(path).model_dump(), valid)
            invalid_values = [
                {**valid, "rules": "false"},
                {**valid, "presidio": 0},
                {**valid, "gliner2": True},
                {"rules": True, "presidio": False},
            ]
            for invalid in invalid_values:
                with self.subTest(config=invalid):
                    path.write_text(json.dumps(invalid), encoding="utf-8")
                    with self.assertRaises(ValidationError):
                        settings.load_config(path)
            path.write_text("{", encoding="utf-8")
            with self.assertRaises(ValidationError):
                settings.load_config(path)
            with self.assertRaises(FileNotFoundError):
                settings.load_config(Path(directory) / "missing.json")

    def test_configuration_uses_project_directory(self):
        self.assertEqual(settings.CONFIG_PATH, Path(app.__file__).resolve().parent / "config.json")
        self.assertEqual(set(settings.load_config().model_dump()), {"rules", "presidio", "gliner"})

    def test_http_endpoints_respect_configuration_loaded_at_startup(self):
        config = settings.DetectorConfig(rules=True, presidio=False, gliner=False)
        with patch.object(app, "load_config", return_value=config) as load_config, \
             patch.object(presidio_engine, "load_presidio") as load_p, \
             patch.object(gliner_engine, "load_gliner") as load_g, \
             TestClient(app.app) as client:
            health = client.get("/health")
            self.assertEqual(health.status_code, 200)
            self.assertEqual(health.json()["configured"], config.model_dump())
            self.assertTrue(health.json()["rules"])
            self.assertFalse(health.json()["presidio"])
            self.assertFalse(health.json()["gliner"])
            response = client.post("/analyze", json={"text": "alice@example.com", "include_ner": True})
            self.assertEqual(response.status_code, 200)
            self.assertEqual({e["source"] for e in response.json()["entities"]}, {"rule"})
            load_config.assert_called_once()
            load_p.assert_not_called()
            load_g.assert_not_called()

    def test_invalid_configuration_prevents_service_startup(self):
        with patch.object(app, "load_config", side_effect=FileNotFoundError("config.json")), \
             patch.object(presidio_engine, "load_presidio") as load_p, \
             patch.object(gliner_engine, "load_gliner") as load_g:
            with self.assertRaises(FileNotFoundError):
                with TestClient(app.app):
                    pass
            load_p.assert_not_called()
            load_g.assert_not_called()


if __name__ == "__main__":
    unittest.main()
