# PII-Detect-Engine

Python + FastAPI PII detection service combining regular expressions, Presidio,
and a local GLiNER2 model.

## 代码结构 / Code structure

```text
app.py                      HTTP routes and application lifecycle
config.json                 Engine enable/disable switches
pii_engine/
  config.py                 Configuration validation and project paths
  schemas.py                Shared request, response, and entity models
  detector.py               Engine orchestration, deduplication, sorting
  engines/
    rules.py                Regex patterns and matching
    presidio.py             Presidio loading, type mapping, detection
    gliner.py               GLiNER2 loading, labels, threshold, inference
tests/
  test_engine_config.py     Configuration and API regression tests
  test_detection.py         Detection and result-merging regression tests
  test_rules.py             Identity-document patterns and false-positive tests
```

修改正则请编辑 `pii_engine/engines/rules.py`；Presidio 类型映射与调用逻辑位于
`pii_engine/engines/presidio.py`；GLiNER2 标签、模型加载和推理位于
`pii_engine/engines/gliner.py`。三个检测器统一接收 `AnalyzeRequest`，返回 `list[Entity]`。
`detector.py` 仅负责按配置编排并合并结果，`app.py` 保留 HTTP 入口。

Optional third-party packages remain lazily imported only when their engine is
enabled. The HTTP API and existing `config.json` switches are unchanged.

## 正则覆盖范围 / Rule coverage

All rules are controlled by the existing `rules` switch. Restart the Python service
after changing rule code. Entity positions cover the matched value only, excluding
labels such as `Passport number:` and JSON quotes.

| Entity type | Coverage | Checks / context |
| --- | --- | --- |
| `email` | Email addresses | Existing email pattern |
| `phone` | Generic separated phone numbers and mainland mobile numbers | Mainland mobile: 11 digits starting with 13–19, optional `86` / `+86` prefix |
| `credit_card` | 13–19 digit candidates | Existing broad pattern; no Luhn check |
| `ip_address` | IPv4 candidates | Existing pattern; no octet-range validation |
| `credential` | Password / API key / secret / private key assignments | Existing assignment pattern |
| `us_ssn` | `AAA-GG-SSSS`, `AAA GG SSSS`, or compact 9 digits | Reject area 000 / 666 / 900–999, group 00, serial 0000; compact form requires SSN / Social Security Number context |
| `identity_number` | Chinese 18-digit ID, including lowercase `x` | Province prefix, nonzero locality suffix, real non-future birth date, nonzero sequence, MOD 11-2 checksum |
| `identity_number` | Legacy Chinese 15-digit ID | Requires 身份证 / 身份證 / ID card context; checks province prefix, locality suffix, date in the 1900s, and sequence; no checksum exists |
| `passport` | Mainland ordinary passport: `G` + 8 digits, `E` + 8 digits, `E` + letter + 7 digits | Second-position letters I / O excluded in the latter format; case-insensitive |
| `passport` | Other passport candidates: 6–9 ASCII letters/digits, containing at least one digit | Requires Passport / Passport Number / Passport No. / 护照 / 護照 context; includes `passportNumber` and `passport_number` fields |

校验仅检查结构，不证明证件已签发或属于真实个人。身份证不核验完整历史县级区划码，
护照规则不覆盖所有国家、外交/公务护照、机读区或带空格的号码。
格式错误、被遮挡或被拆分的证件号仍可能漏检；Presidio / GLiNER2 可独立提供补充检测。

Specific identity-document findings take precedence over overlapping generic
phone/card candidates within the rules engine. Equal type/span findings keep the
highest fixed score. Other detection sources retain their existing merge behavior.
Presidio's `US_SSN` is now mapped to `us_ssn` to match the new rule (previously
`identity_number`). The C# gateway's default risk mapping treats the new type as
ordinary PII to redact.

Format references:

- [SSA: invalid SSN groups](https://www.ssa.gov/employer/randomizationfaqs.html)
- [Beijing Public Security Bureau: Chinese ID structure](https://gaj.beijing.gov.cn/hudong/rddf/202003/t20200331_1771804.html)
- [Shanghai Business School: checksum weights and mapping](https://jiaowc.sbs.edu.cn/docs/2022-06/6d3cf78d578748f39fc5e2492c9eb0c5.pdf)
- [National Immigration Administration: ordinary passport numbering](https://www.nia.gov.cn/n741440/n741547/c1197066/content.html)

## 检测引擎配置 / Engine configuration

Edit `config.json` next to `app.py` to independently enable or disable each engine:

```json
{
  "rules": true,
  "presidio": false,
  "gliner": true
}
```

| Key | Controls |
| --- | --- |
| `rules` | 正则规则 / Regular-expression detection |
| `presidio` | Presidio 初始化和检测 / Initialization and detection |
| `gliner` | GLiNER2 模型加载和推理 / Model loading and inference |

配置文件默认全部开启。修改后需重启 Python 服务；不支持热更新。
关闭 Presidio 或 GLiNER2 时，不导入相应引擎，也不初始化或加载模型。

All engines are enabled in the shipped configuration. Restart the Python service
after editing; configuration is loaded once at startup. Disabled optional engines
are not imported, initialized, or loaded. Dependency installation in `start.ps1`
still installs the full `requirements.txt` regardless of these switches.

All three keys are required and must be JSON booleans (`true` / `false`, not strings).
Unknown keys, invalid values, or a missing file prevent startup instead of silently
using different settings. The file is resolved relative to `app.py`, independently
of the current working directory. It is separate from the model's `models/.../config.json`.

请求字段 `include_ner=false` 仍可跳过本次 GLiNER2 推理，但不能覆盖全局关闭配置。
C# 网关目前固定发送 `include_ner=true`，仍受本配置文件中的 `gliner` 开关控制。

The request field `include_ner=false` skips GLiNER2 for that request; `true` cannot
override `gliner=false`. Presidio and rules are unaffected by `include_ner`.

`GET /health` reports `configured` (the switches) and top-level `rules`, `presidio`,
and `gliner` availability. An enabled optional engine may still be unavailable if
its dependencies or model are missing. `/analyze` also returns availability in
`engine`; availability does not indicate whether GLiNER2 ran for that request.

全部关闭时检测结果为空，网关会将其视为没有发现 PII；这会关闭该链路的 PII 防护。
If all engines are disabled, detection returns no entities and the gateway treats
the request as having no detected PII.

Existing environment variables `GLINER_MODEL_PATH`, `GLINER_THRESHOLD` (default
`0.65`), and `OFFLINE_MODE` are unchanged. The offline flag does not enforce all
network restrictions; enabling Presidio may trigger language-model downloads.

## Run

```powershell
.\start.ps1
```

The service listens on `http://127.0.0.1:8000`. The default local GLiNER2 model path
is resolved relative to the project directory. Download it explicitly when needed:

```powershell
.\.venv\Scripts\python.exe .\download_model.py
```

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Tests use fake optional engines and do not download or load model weights.

