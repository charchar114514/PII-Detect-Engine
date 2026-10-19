"""Synthetic/documentation examples; no real personal records are required."""
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import app
from pii_engine.config import DetectorConfig
from pii_engine.engines.rules import RulesDetector
from pii_engine.schemas import AnalyzeRequest


def with_checksum(first_seventeen: str) -> str:
    weights = (7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2)
    remainder = sum(int(digit) * weight for digit, weight in zip(first_seventeen, weights)) % 11
    return first_seventeen + "10X98765432"[remainder]


class IdentityRuleTests(unittest.TestCase):
    def values(self, text, kind):
        return [text[e.start:e.end] for e in RulesDetector().analyze(AnalyzeRequest(text=text))
                if e.type == kind]

    def test_formatted_ssns(self):
        for value in ("219-09-9999", "219 09 9999"):
            with self.subTest(value=value):
                self.assertEqual(self.values(f"Contact: {value}.", "us_ssn"), [value])

    def test_compact_ssn_requires_context_and_has_exact_offsets(self):
        for text in ('SSN: 219099999', 'Social Security Number = 219099999',
                     '{"ssn": "219099999"}'):
            with self.subTest(text=text):
                self.assertEqual(self.values(text, "us_ssn"), ["219099999"])
        self.assertEqual(self.values("Order 219099999", "us_ssn"), [])

    def test_ssn_invalid_groups_and_boundaries(self):
        for value in ("000-12-3456", "666-12-3456", "900-12-3456", "999-12-3456",
                      "219-00-9999", "219-09-0000", "219-09 9999",
                      "A219-09-9999", "219-09-99990", "SSN: 000123456"):
            with self.subTest(value=value):
                self.assertEqual(self.values(value, "us_ssn"), [])

    def test_chinese_18_digit_id_with_x_and_chinese_context(self):
        value = "11010519491231002X"
        for text, expected in ((f"身份证号码：{value}", value),
                               (f"身份證號碼：{value.lower()}。", value.lower()),
                               (value, value)):
            with self.subTest(text=text):
                self.assertEqual(self.values(text, "identity_number"), [expected])

    def test_chinese_id_numeric_checksum_and_leap_day(self):
        value = with_checksum("11010520000229001")
        self.assertEqual(self.values(value, "identity_number"), [value])

    def test_chinese_id_rejects_checksum_date_region_and_sequence_errors(self):
        invalid = [
            "110105194912310021",  # Incorrect checksum.
            with_checksum("11010520010229001"),  # Not a leap year.
            with_checksum("11010520001301001"),
            with_checksum("11010520990101001"),  # Future birthday.
            with_checksum("99010519900101001"),
            with_checksum("11000019900101001"),
            with_checksum("11010519900101000"),
            "A11010519491231002X", "11010519491231002X9",
        ]
        for value in invalid:
            with self.subTest(value=value):
                self.assertEqual(self.values(value, "identity_number"), [])

    def test_legacy_id_requires_context(self):
        value = "130503670401001"
        for prefix in ("身份证号：", "身份證號碼：", "Chinese ID card number: "):
            self.assertEqual(self.values(prefix + value, "identity_number"), [value])
        self.assertEqual(self.values("Order " + value, "identity_number"), [])
        self.assertEqual(self.values("身份证：130503670231001", "identity_number"), [])

    def test_mainland_passports(self):
        for value in ("G12345678", "E12345678", "EA1234567", "EZ1234567", "ea1234567"):
            with self.subTest(value=value):
                self.assertEqual(self.values("证件：" + value + "。", "passport"), [value])

    def test_generic_passports_require_context_and_only_return_number(self):
        for text, expected in (
            ("Passport number: A12345678", "A12345678"),
            ("passportnumber=123456789", "123456789"),
            ("Passport No. AB123456", "AB123456"),
            ("护照号：AB123456", "AB123456"),
            ("護照號碼：AB123456", "AB123456"),
            ('{"passportNumber": "AB123456"}', "AB123456"),
        ):
            with self.subTest(text=text):
                self.assertEqual(self.values(text, "passport"), [expected])
        self.assertEqual(self.values("Order AB123456", "passport"), [])

    def test_passport_boundaries_and_false_positives(self):
        for text in ("EI1234567", "EO1234567", "AE12345678", "EA12345678",
                     "E123456789", "Passport expired", "Passport number: ABCDEF",
                     "Passport number: 12345", "Passport number: 1234567890",
                     "otherpassportnumber: AB123456"):
            with self.subTest(text=text):
                self.assertEqual(self.values(text, "passport"), [])

    def test_compact_mainland_mobile(self):
        for value in ("13800138000", "+8613800138000", "+86 13800138000", "86-13800138000"):
            with self.subTest(value=value):
                self.assertIn(value, self.values("电话：" + value, "phone"))

    def test_specific_id_is_not_reported_as_card_or_phone(self):
        text = "身份证：" + with_checksum("11010519900101001")
        entities = RulesDetector().analyze(AnalyzeRequest(text=text))
        self.assertEqual([entity.type for entity in entities], ["identity_number"])

    def test_rules_only_http_response_for_mixed_identifiers(self):
        text = "SSN: 219-09-9999; 身份证：11010519491231002X; Passport: EA1234567"
        with patch.object(app, "load_config", return_value=DetectorConfig(
            rules=True, presidio=False, gliner=False,
        )), TestClient(app.app) as client:
            response = client.post("/analyze", json={"text": text})
        self.assertEqual(response.status_code, 200)
        entities = response.json()["entities"]
        self.assertEqual([entity["type"] for entity in entities], ["us_ssn", "identity_number", "passport"])
        self.assertEqual([text[e["start"]:e["end"]] for e in entities],
                         ["219-09-9999", "11010519491231002X", "EA1234567"])


if __name__ == "__main__":
    unittest.main()
