---
library_name: gliner2
language:
- en
- fr
- es
- de
- it
- pt
- nl
tags:
- pii
- ner
- privacy
- redaction
- gliner2
- information-extraction
- span-extraction
license: apache-2.0
datasets:
- synthetic
pipeline_tag: token-classification
---
<div style="display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 16px;">
  <a href="https://arxiv.org/abs/2605.09973" target="_blank" rel="noreferrer" style="text-decoration:none;">
    <img src="https://img.shields.io/badge/arXiv-2605.07982-b31b1b.svg?logo=arxiv" alt="arXiv Paper" style="vertical-align:middle;">
  </a>
  <a href="https://fastino.ai?utm_source=huggingface" target="_blank" rel="noreferrer" style="text-decoration:none;">
    <img src="https://img.shields.io/badge/Deploy-GLiNER2%20PII-FF7345" alt="Deploy GLiNER2-PII model with Pioneer" style="vertical-align:middle;">
  </a>
  <a href="https://x.com/fastinoAI" target="_blank" rel="noreferrer" style="text-decoration:none;">
    <img src="https://img.shields.io/twitter/follow/:fastinoAI" alt="Follow @fastinoAI" style="vertical-align:middle;">
  </a>
</div>

# GLiNER2-PII: Multilingual PII Detection & Masking

**GLiNER2-PII** is a fine-tune of the [GLiNER2](https://github.com/fastino-ai/GLiNER2) model (205M parameters) for detecting and masking personally identifiable information across **42 entity types** and **7 languages**.

Trained entirely on a constraint-driven synthetic corpus of 4,910 annotated texts, it achieves the **highest span-level F1 (0.477)** on the [SPY benchmark](https://aclanthology.org/2025.naacl-srw.23/) among four compared systems — including OpenAI Privacy Filter, NVIDIA GLiNER-PII, and urchade/gliner\_multi\_pii-v1.

📄 **[Technical Report](https://arxiv.org/abs/2605.09973)**  
🔗 **[GitHub](https://github.com/fastino-ai/GLiNER2)**

---

## Quick Start

```bash
pip install gliner2
```

```python
from gliner2 import GLiNER2

model = GLiNER2.from_pretrained("fastino/gliner2-privacy-filter-PII-multi")

text = "Email john.smith@acme.com or call +1 415 555 0199."
labels = ["email", "phone_number", "person"]

result = model.extract_entities(
    text,
    labels,
    threshold=0.5,
    include_confidence=True,
    include_spans=True,
)

print(result)
```

You can pass **any subset** of the 42 supported labels — the model conditions on the labels you provide at inference time.

---

## Supported PII Labels (42 types)

| Group | Labels |
|---|---|
| **Person / names** | `person`, `full_name`, `first_name`, `middle_name`, `last_name`, `date_of_birth` |
| **Contact / address** | `email`, `phone_number`, `address`, `street_address`, `city`, `state_or_region`, `postal_code`, `country` |
| **Government / tax IDs** | `government_id`, `national_id_number`, `passport_number`, `drivers_license_number`, `license_number`, `tax_id`, `tax_number` |
| **Banking / payment** | `bank_account`, `account_number`, `routing_number`, `iban`, `payment_card`, `card_number`, `card_expiry`, `card_cvv` |
| **Digital identity** | `username`, `ip_address`, `account_id`, `sensitive_account_id` |
| **Secrets / credentials** | `password`, `secret`, `api_key`, `access_token`, `recovery_code` |
| **Sensitive dates** | `sensitive_date`, `document_date`, `expiration_date`, `transaction_date` |

---

## Benchmark Results (SPY)

Evaluated on the [SPY benchmark](https://aclanthology.org/2025.naacl-srw.23/) (Savkin et al., 2025) with exact-match span-level metrics:

| Model | Legal P | Legal R | Legal F1 | Medical P | Medical R | Medical F1 | **Avg F1** |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **fastino/gliner2-pii-v1** | .346 | **.750** | **.473** | .369 | **.686** | **.480** | **.477** |
| nvidia/gliner-PII | .343 | .452 | .390 | .368 | .465 | .411 | .400 |
| urchade/gliner\_multi\_pii-v1 | **.467** | .317 | .377 | **.518** | .351 | .419 | .398 |
| openai/privacy-filter | .242 | .656 | .354 | .287 | .692 | .406 | .380 |

### Key takeaways

- **Highest F1** on both legal and medical domains.
- **Best recall** among GLiNER-based detectors (0.718 avg) — critical for redaction workflows where missed spans are data leaks.
- Consistent performance across domains (< 2-point F1 difference).

---

## When to Use This Model

| Use case | Why GLiNER2-PII |
|---|---|
| **PII redaction / masking** | High recall minimises missed sensitive spans |
| **Data governance & GDPR/CCPA compliance** | 42 fine-grained types enable policy-specific routing |
| **Training-data hygiene** | Exact character spans for precise masking before model training |
| **Multi-language pipelines** | Trained on EN, FR, ES, DE, IT, PT, NL formats |

---

## Redaction Example

```python
def redact(text, labels, threshold=0.5):
    model = GLiNER2.from_pretrained("fastino/gliner2-pii-v1")
    result = model.extract_entities(
        text, labels, threshold=threshold,
        include_spans=True,
    )
    entities = result.get("entities", {})
    spans = []
    for label, values in entities.items():
        for value in values:
            start = text.find(value)
            if start != -1:
                spans.append((start, start + len(value), label))

    spans.sort(key=lambda s: s[0], reverse=True)
    redacted = text
    for start, end, label in spans:
        redacted = redacted[:start] + f"[{label.upper()}]" + redacted[end:]
    return redacted


text = "Please contact Maria Jensen at maria.jensen@example.dk or +45 20 12 34 56."
labels = ["person", "email", "phone_number"]
print(redact(text, labels))
# "Please contact [PERSON] at [EMAIL] or [PHONE_NUMBER]."
```

---

## Training Details

| Detail | Value |
|---|---|
| Base model | GLiNER2 (205M parameters) |
| Training data | 4,910 synthetic annotated texts |
| PII mentions | 129,951 total (mean 26.5 per example) |
| Generator | GPT-5.4 (temperature 0.01) |
| Data framework | Constraint-driven generation (same framework as [Pioneer Agent](https://arxiv.org/abs/2604.09791)) |
| Languages | English, French, Spanish, German, Italian, Portuguese, Dutch |
| Label types | 42 PII entity types across 7 semantic groups |

---

## Limitations

- **Precision** (0.35–0.37 on SPY) leaves room for improvement; the model tends to over-predict `name` entities, sometimes confusing common nouns, organisation names, and product names with personal names.
- Evaluated on a **single benchmark** (SPY) covering two domains. Broader multilingual and fine-grained evaluation is ongoing.
- Training data is **fully synthetic** and has not been validated by human annotators.
- Performance on **non-European** locales and scripts has not been measured.

### Improving precision

For production use, consider:
- Per-label confidence thresholds (raise threshold for `person` / `full_name`)
- Dictionary-based filtering for common false positives
- Calibration on a small domain-specific development set

---

## Citation

```bibtex
@misc{fastino2026gliner2pii,
  title   = {GLiNER2-PII: Multilingual PII Extraction via Synthetic Fine-Tuning},
  author  = {{Fastino AI Team}},
  year    = {2026},
  url     = {https://huggingface.co/fastino/gliner2-pii-v1}
}
```

### Related work

```bibtex
@misc{zaratiana2026gliner2piimultilingualmodelpersonally,
      title={GLiNER2-PII: A Multilingual Model for Personally Identifiable Information Extraction}, 
      author={Urchade Zaratiana and Ash Lewis and George Hurn-Maloney},
      year={2026},
      eprint={2605.09973},
      archivePrefix={arXiv},
      primaryClass={cs.CL},
      url={https://arxiv.org/abs/2605.09973}, 
}

@inproceedings{zaratiana-etal-2025-gliner2,
  title     = {GLiNER2: Schema-Driven Multi-Task Learning for Structured Information Extraction},
  author    = {Zaratiana, Urchade and Pasternak, Gil and Boyd, Oliver and Hurn-Maloney, George and Lewis, Ash},
  booktitle = {Proceedings of EMNLP 2025: System Demonstrations},
  year      = {2025}
}

@inproceedings{zaratiana-etal-2024-gliner,
  title     = {GLiNER: Generalist Model for Named Entity Recognition using Bidirectional Transformer},
  author    = {Zaratiana, Urchade and Tomeh, Nadi and Holat, Pierre and Charnois, Thierry},
  booktitle = {Proceedings of NAACL 2024},
  year      = {2024}
}

@misc{atreja2026pioneeragent,
  title  = {Pioneer Agent: Continual Improvement of Small Language Models in Production},
  author = {Atreja, Dhruv and White, Julia and Nayak, Nikhil and Zhang, Kelton and Princis, Henrijs and Hurn-Maloney, George and Lewis, Ash and Zaratiana, Urchade},
  year   = {2026},
  url    = {https://arxiv.org/abs/2604.09791}
}
```

---

## License

Apache 2.0