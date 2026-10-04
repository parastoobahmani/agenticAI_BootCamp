# مسئلهٔ ۱ – بخش ۲: تشخیص اطلاعات گمشده و قدم بعدی

> برنچ: `ali-moghadasi` · مسئول: علی مقدسی · پروژهٔ نهایی بوت‌کمپ Agentic AI کوئرا (دستیار پشتیبانی فنی Streamlit)

## خلاصه

این بخش تصمیم می‌گیرد **قدم بعدیِ** یک پروندهٔ پشتیبانی چه باشد. ورودی‌اش خودِ پرونده (عنوان، متن و گفت‌وگو) و خروجیِ بخش ۱-۱ است: شواهد بازیابی‌شده و فرضیه‌هایی که علت مشکل را توضیح می‌دهند. سیستم اول از متن پرونده بیرون می‌کشد چه چیزهایی معلوم است و کاربر چه کارهایی را قبلاً امتحان کرده. بعد برای هر فرضیه مشخص می‌کند اگر درست باشد، چه مشاهده‌ای انتظار می‌رود. با قاعدهٔ بیز احتمال فرضیه‌ها را بر اساس واقعیت‌های معلوم به‌روز می‌کند و سراغ سؤال یا بررسی‌ای می‌رود که بیشترین **بهرهٔ اطلاعاتی مورد انتظار** (Expected Information Gain) را نسبت به زحمتش برای کاربر دارد. یعنی سؤالی که جوابش واقعاً میان توضیح‌های محتمل فرق می‌گذارد.

نتیجه یکی از سه تصمیم است:

- **`propose_answer`**: یک فرضیه به‌طور قاطع جلوتر است و منبع معتبر پشتش است. این تصمیم به بخش ۱-۳ می‌رود تا پاسخ نوشته شود.
- **`request_information`**: حداکثر دو سؤال یا بررسی هدفمند، هر کدام با دلیل.
- **`escalate`**: پاسخ قابل‌دفاعی پیدا نشده. محدودیت‌ها و مسیر ادامهٔ بررسی صریحاً گفته می‌شوند.

سیستم چیزهایی را که قبلاً گفته شده دوباره نمی‌پرسد. آزمایشی را که کاربر انجام داده تکرار نمی‌کند، و اگر کاربر گفته کاری را کرده ولی نتیجه‌اش را نگفته، فقط نتیجه را می‌پرسد. یک گزارش مشابه هم به‌تنهایی برای نتیجه‌گیری کافی نیست.

---

## فهرست

1. [جایگاه در خط لوله](#جایگاه-در-خط-لوله)
2. [ابزارها و وابستگی‌ها](#ابزارها-و-وابستگیها)
3. [نصب و اجرا](#نصب-و-اجرا)
4. [ورودی و فرضیات](#ورودی-و-فرضیات)
5. [خروجی](#خروجی)
6. [روش کار (الگوریتم)](#روش-کار-الگوریتم)
7. [نحوهٔ اتصال به بخش‌های دیگر](#نحوهٔ-اتصال-به-بخشهای-دیگر)
8. [پیکربندی](#پیکربندی)
9. [توسعه و افزودن قابلیت](#توسعه-و-افزودن-قابلیت)
10. [آزمون‌ها](#آزمونها)
11. [ساختار پوشه‌ها](#ساختار-پوشهها)
12. [مراحل ساخت (تاریخچهٔ کامیت‌ها)](#مراحل-ساخت-تاریخچهٔ-کامیتها)
13. [محدودیت‌ها و کارهای بعدی](#محدودیتها-و-کارهای-بعدی)

---

## جایگاه در خط لوله

```
 پرونده (title, body, comments)
          │
          ▼
 ┌──────────────────────────┐      evidence + hypotheses
 │ ۱-۱ یافتن و ترکیب شواهد  │ ───────────────────────────┐
 └──────────────────────────┘                            ▼
                                     ┌────────────────────────────────────────┐
 پرونده ───────────────────────────▶ │ ۱-۲ تشخیص اطلاعات گمشده و قدم بعدی     │  ← این برنچ
                                     │ (missing_info)                         │
                                     └────────────────────────────────────────┘
                                                         │  NextStepReport (JSON)
                                                         ▼
                                     ┌────────────────────────────────────────┐
                                     │ ۱-۳ تهیهٔ پاسخ و جمع‌بندی پرونده        │
                                     └────────────────────────────────────────┘
```

طبق صورت پروژه فرض شده بخش ۱-۱ انجام شده و خروجی‌اش با قالبی که در بخش [ورودی و فرضیات](#ورودی-و-فرضیات) آمده در دسترس است. در برنچ `finding_combining_evidence` هنوز کدی نبود، پس قالب ورودی را خودم تعریف کردم و برای هماهنگی، JSON Schema آن را در `schemas/` گذاشتم.

---

## ابزارها و وابستگی‌ها

| ابزار | نسخه | کاربرد |
|---|---|---|
| Python | ≥ 3.10 (روی 3.13 تست شده) | زبان پیاده‌سازی |
| [pydantic](https://docs.pydantic.dev) v2 | ≥ 2.5 | قرارداد داده‌ها، اعتبارسنجی ورودی و خروجی، تولید JSON Schema |
| [packaging](https://packaging.pypa.io) | ≥ 23 | مقایسهٔ نسخه‌ها و بازه‌های PEP 440 مثل `<1.33.0` |
| [pytest](https://pytest.org) | ≥ 8 (اختیاری، `dev`) | آزمون‌ها |
| [openai](https://github.com/openai/openai-python) | ≥ 1.30 (اختیاری، `llm`) | کلاینت سازگار با OpenAI برای درگاه متیس، فقط با `--llm` |
| [uv](https://github.com/astral-sh/uv) | اختیاری | ساخت سریع محیط مجازی (با `pip` معمولی هم کار می‌کند) |

**چرا LangChain یا LangGraph نه؟** این بخش منطق تصمیم است، نه Orchestration. هستهٔ آن قطعی (deterministic) است، بدون فراخوانی مدل اجرا می‌شود و هزینهٔ API ندارد. پس آزمون‌پذیر و تکرارپذیر است و از بودجهٔ ۵ دلاری تیم چیزی مصرف نمی‌کند. LLM فقط به‌عنوان یک افزونهٔ اختیاری برای فهم فرضیه‌های آزاد آمده و با چند خط کد ساده کار می‌کند.

---

## نصب و اجرا

```bash
git checkout ali-moghadasi
```

```bash
uv venv .venv && uv pip install -p .venv -e ".[dev]"
```

یا با pip معمولی:

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
```

اجرای نمونهٔ صورت پروژه («روی سیستم خودم باز می‌شود، روی سرور در صفحهٔ بارگذاری می‌ماند، نصب دوباره کمکی نکرد»):

```bash
.venv/bin/missing-info analyze examples/stuck_loading_on_server.json --format markdown
```

خروجی JSON (برای بخش ۱-۳):

```bash
.venv/bin/missing-info analyze examples/stuck_loading_on_server.json --output report.json
```

خواندن ورودی از stdin:

```bash
cat examples/no_evidence_found.json | .venv/bin/missing-info analyze -
```

تولید دوبارهٔ JSON Schema قرارداد ورودی و خروجی:

```bash
.venv/bin/missing-info schema --output-dir schemas
```

### حالت اختیاری با LLM

```bash
uv pip install -p .venv -e ".[llm]"
```

```bash
export METIS_API_KEY=...   # هرگز در کد یا گیت قرار ندهید (.env در .gitignore است)
```

```bash
.venv/bin/missing-info analyze examples/stuck_loading_on_server.json --llm --llm-cache runs/llm_cache.json
```

| متغیر محیطی | پیش‌فرض | توضیح |
|---|---|---|
| `METIS_API_KEY` | (الزامی در حالت `--llm`) | کلید درگاه متیس |
| `METIS_BASE_URL` | `https://api.metisai.ir/openai/v1` | نشانی endpoint سازگار با OpenAI (با مستندات متیس تطبیق دهید) |
| `MISSING_INFO_MODEL` | `gpt-4o-mini` | مدل؛ با `--model` هم قابل تغییر است |

کنترل هزینه در حالت LLM:

- برای هر فرضیه فقط یک درخواست کوتاه JSON-mode فرستاده می‌شود، با `temperature=0` و سقف ۴۰۰ توکن خروجی.
- سقف ۵۰ درخواست در هر اجرا (`BudgetExceeded`).
- `--llm-cache` پاسخ‌ها را ضبط و بعداً بازپخش می‌کند، پس اجرای دوبارهٔ ارزیابی هزینه‌ای ندارد.
- آمار درخواست‌ها و توکن‌ها روی stderr چاپ می‌شود.
- اگر LLM خطا بدهد، تحلیل نمی‌شکند و سیستم به قواعد برمی‌گردد.

---

## ورودی و فرضیات

ورودی یک شیء `AnalysisInput` است (اسکیما: [`schemas/analysis_input.schema.json`](schemas/analysis_input.schema.json)):

```json
{
  "case": { "case_id": "...", "title": "...", "body": "...", "author": "reporter", "comments": [ ... ] },
  "evidence_bundle": { "evidence": [ ... ], "hypotheses": [ ... ] }
}
```

### `case`: پرونده

| فیلد | نوع | توضیح |
|---|---|---|
| `case_id` | str | شمارهٔ گزارش یا شناسهٔ پرونده |
| `title`, `body` | str | عنوان و متن گزارش |
| `url` | str? | `html_url` |
| `author` | str? | نام کاربری گزارش‌دهنده؛ برای جدا کردن پیام‌های خودِ او |
| `created_at` | datetime? | |
| `comments[]` | `{id, body, created_at?, author?, author_association}` | گفت‌وگو **به ترتیب زمانی** |

برای ساختن مستقیم از خروجی GitHub REST API، `Case.from_github(issue_json, comments_json)` آماده است. این تابع Pull Requestها را (که فیلد `pull_request` دارند) رد می‌کند.

### `evidence_bundle.evidence[]`: شواهد بخش ۱-۱

| فیلد | نوع | توضیح |
|---|---|---|
| `evidence_id` | str (یکتا) | مثلاً `doc:<path>#<section>` یا `issue:<number>` |
| `source_type` | `doc` \| `issue` \| `release_note` | نوع منبع |
| `title`, `url`, `section` | str | ارجاع قابل بررسی |
| `snippet` | str | متن مرتبط |
| `source_version` | str? | commit مستندات، نسخهٔ release یا تاریخ snapshot |
| `relevance` | float ∈ [0,1] | امتیاز بازیابی |
| `relation` | str? | ارتباط این منبع با نشانه‌ها و محیط کاربر |
| `claim_kind` | `reported_fact` \| `documented` \| `hypothesis` | تمایز «واقعیت گزارش‌شده»، «توضیح مستند» و «فرضیهٔ دستیار» (خواستهٔ بخش ۱-۱) |
| `fixed_in_version` | str? | نسخه‌ای که مشکل در آن رفع شده (از release note یا issue بسته‌شده) |
| `author_association` | str? | برای شواهد issue: نسبت نویسنده با مخزن |

### `evidence_bundle.hypotheses[]`: فرضیه‌های بخش ۱-۱

| فیلد | نوع | توضیح |
|---|---|---|
| `hypothesis_id` | str (یکتا) | |
| `statement` | str | توضیح علت احتمالی (متن آزاد) |
| `confidence` | float ∈ [0,1] | امتیاز اولیهٔ بخش ۱-۱؛ اینجا به prior تبدیل می‌شود |
| `evidence_ids` | list[str] | شواهد پشتیبان؛ باید در `evidence` وجود داشته باشند |
| `expectations` | dict? (اختیاری) | پیش‌بینی‌های فرضیه، مثلاً `{"reverse_proxy": {"values": ["yes"]}, "streamlit_version": {"version_spec": "<1.33.0"}}` |

### فرضیاتی که دربارهٔ ورودی کرده‌ام

1. بخش ۱-۱ علاوه بر شواهد، **فهرستی از فرضیه‌ها با امتیاز** هم می‌دهد. بازیابی چند متن شبیه بدون جمع‌بندی برای این بخش کافی نیست.
2. `confidence`ها احتمال نرمال‌شده نیستند، فقط امتیازهای نسبی‌اند. این بخش آن‌ها را نرمال می‌کند و ۲۰٪ احتمال را برای «علتی که هیچ‌کدام از فرضیه‌ها نگفته‌اند» کنار می‌گذارد.
3. `expectations` **اختیاری** است. اگر بخش ۱-۱ آن را ندهد، این بخش آن را با قواعد کلیدواژه‌ای یا (در صورت فعال بودن) با LLM از روی `statement` و شواهد استنتاج می‌کند. اگر داده شود، بر استنتاج اولویت دارد.
4. پرونده فقط شامل اطلاعاتی است که **در لحظهٔ تحلیل** قابل مشاهده است. کنترل نشت داده و آشکارسازی تدریجی پاسخ‌های کاربر در ارزیابی بر عهدهٔ لایهٔ ارزیابی است.
5. واقعیت‌های محیطی فقط از پیام‌های **خودِ گزارش‌دهنده** استخراج می‌شوند. پیام نگه‌دارنده‌ها (OWNER/MEMBER/COLLABORATOR) و «من هم همین‌طور» کاربران دیگر کنار گذاشته می‌شوند، چون محیط آن‌ها با محیط کاربر یکی نیست. مثلاً «fixed in 1.30» نسخهٔ کاربر نیست.
6. زبان داده‌ها عمدتاً انگلیسی است. قواعد استخراج انگلیسی‌اند و چند الگوی فارسی هم برای مثال صورت پروژه دارند. زبان خروجی (متن سؤال‌ها) انگلیسی و ثابت است.

---

## خروجی

خروجی یک شیء `NextStepReport` است (JSON، اسکیما: [`schemas/next_step_report.schema.json`](schemas/next_step_report.schema.json)). با `--format markdown` نسخهٔ خوانا برای انسان هم تولید می‌شود. نمونه‌ها در [`examples/outputs/`](examples/outputs) هستند.

| فیلد | نوع | توضیح |
|---|---|---|
| `schema_version` | `"1.0"` | نسخهٔ قرارداد |
| `case_id` | str | |
| `decision` | `{type, rationale, hypothesis_id?}` | `propose_answer` \| `request_information` \| `escalate`، همراه با دلیل |
| `next_steps[]` | `Probe` | حداکثر `max_probes` (پیش‌فرض ۲) قدم، به ترتیب اولویت |
| `known_facts[]` | `KnownFact` | آنچه معلوم است: `facet`، `value`، `status` (`observed` یا `performed_outcome_unknown`)، `origin` (محل و جملهٔ منبع) و `superseded` (اصلاحیه‌های کاربر) |
| `missing_information[]` | `MissingFacet` | آنچه هنوز نامعلوم است و برای کدام فرضیه‌ها مهم است، با بهرهٔ اطلاعاتی |
| `hypotheses[]` | `RankedHypothesis` | prior و posterior، قدرت شواهد (`strong`/`weak`/`none`)، واقعیت‌های سازگار و ناسازگار، و منبع expectationها |
| `skipped_probes[]` | `{facet, reason}` | چیزهایی که عمداً دوباره پرسیده نشدند |
| `limitations[]` | list[str] | محدودیت اطلاعات و ابهام‌های باقی‌مانده |

هر `Probe` شامل این‌هاست:

- `facet`
- `kind`: `question` (کاربر جواب را می‌داند)، `check` (باید کاری اجرا کند) یا `follow_up` (کار را کرده ولی نتیجه را نگفته)
- `basis`: `information_gain` یا `fallback`
- `text`: متن آمادهٔ پرسش
- `rationale`: مثلاً «'yes' favours h_proxy; 'no' favours h_subpath, …»
- `distinguishes`، `expected_information_gain` (بیت)، `cost` و `score`

نمونهٔ خلاصه‌شده برای مثال صورت پروژه:

```json
{
  "decision": { "type": "request_information", "rationale": "No explanation is clearly ahead (...)" },
  "next_steps": [
    { "facet": "reverse_proxy", "kind": "question",
      "text": "Is the app served through a reverse proxy or load balancer (...)?",
      "rationale": "'yes' favours h_proxy_websocket; 'no' favours h_subpath, h_cors_xsrf, h_broken_env, an unlisted cause",
      "expected_information_gain": 0.1021, "cost": 1 },
    { "facet": "served_under_subpath", "kind": "question", "...": "..." }
  ],
  "skipped_probes": [
    { "facet": "reinstall_resolves", "reason": "already performed (body: \"Reinstalling did not help.\") -> reinstall_resolves=no" }
  ],
  "limitations": [ "h_broken_env conflicts with reported facts: reinstall_resolves=no." ]
}
```

---

## روش کار (الگوریتم)

```
case ──▶ extraction ──▶ known facts ─────────────┐
                                                 ▼
bundle ─▶ profiling ──▶ expectations ──▶ belief model (Bayes) ──▶ probes (EIG/cost) ──▶ decision policy ──▶ report
```

### ۱. Facetها (`facets.py`)

Facet یعنی یک «بُعد اطلاعاتی» که می‌تواند میان علت‌ها فرق بگذارد. دو نوع دارد:

- **attribute**: چیزی که کاربر می‌داند، مثل نسخهٔ Streamlit، محل استقرار، وجود reverse proxy یا sub-path، و این‌که مشکل روی سیستم خودش هم پیش می‌آید یا نه.
- **check**: کاری که کاربر باید انجام دهد، مثل نگاه کردن به خطای WebSocket در کنسول مرورگر، `curl` روی `/_stcore/health`، امتحان مرورگر دیگر، ارتقا، نصب مجدد یا پاک کردن cache.

هر facet متن دقیق پرسش، نوع مقدار (category، version یا text) و **هزینه** (زحمت کاربر از ۱ تا ۳) دارد.

### ۲. استخراج آنچه معلوم است (`extraction.py`)

استخراج با قواعد regex محافظه‌کارانه انجام می‌شود. اگر چیزی صریح گفته نشده باشد، **نامعلوم می‌ماند**؛ حدس زدن نسخه یا نتیجهٔ آزمایش ممنوع است.

- فقط پیام‌های گزارش‌دهنده بررسی می‌شوند. HTML commentهای قالب issue حذف می‌شوند و false-positiveهای رایج کنار گذاشته می‌شوند: `st.container`، «Apache Arrow»، لینک «Open in Streamlit Cloud» و نفی‌هایی مثل «doesn't work locally».
- هر واقعیت جملهٔ منبعش را به‌عنوان `origin.quote` نگه می‌دارد، پس قابل بررسی است.
- **اصلاح کاربر**: در طول گفت‌وگو جملهٔ جدیدتر برنده است و جملهٔ قبلی در `superseded` و `limitations` ثبت می‌شود.
- **کارهای انجام‌شده**: «Reinstalling didn't help» به `reinstall_resolves=no` تبدیل می‌شود و این بررسی دیگر پیشنهاد نمی‌شود. اگر نتیجه گفته نشده باشد («I checked the console»)، وضعیت `performed_outcome_unknown` می‌گیرد و فقط نتیجه پرسیده می‌شود (`follow_up`).

### ۳. تبدیل فرضیه به پیش‌بینی (`profiling.py`)

هر فرضیه به مجموعه‌ای از expectationها تبدیل می‌شود. مثلاً «reverse proxy هدرهای WebSocket را رد نمی‌کند» یعنی `reverse_proxy=yes`، `websocket_error_in_console=yes`، `health_endpoint_ok=yes` و `reproduces_locally=no`. منابع به ترتیب اولویت این‌ها هستند:

1. `expectations` که بخش ۱-۱ داده
2. پروفایلرهای قابل‌تعویض به ترتیب: `LLMProfiler` (اختیاری) و بعد `RuleBasedProfiler`

`RuleBasedProfiler` خانواده‌های رایج خطا را پوشش می‌دهد: proxy/WebSocket، CORS/XSRF، sub-path، در دسترس نبودن سرور، مشکل خاص مرورگر، محیط خراب، cache، محدودیت منابع و سیستم‌عامل. از عبارت‌های «introduced in X / fixed in Y» یا از `fixed_in_version` شواهد، بازهٔ نسخه هم می‌سازد (مثلاً `streamlit_version <1.33.0` و `upgrade_resolves=yes`). expectationهای نامعتبر با هشدار حذف می‌شوند و تحلیل نمی‌شکند.

### ۴. مدل باور و بهرهٔ اطلاعاتی (`scoring.py`)

- **Prior**: confidenceهای بخش ۱-۱ نرمال می‌شوند و به `1 − 0.2` مقیاس می‌گیرند. ۰٫۲ باقی‌مانده سهم فرضیهٔ `unlisted_cause` است. این فرضیه چیزی پیش‌بینی نمی‌کند و جلوی اطمینان کاذب را می‌گیرد: اگر واقعیت‌ها با همهٔ فرضیه‌ها ناسازگار باشند، احتمال به آن منتقل می‌شود.
- **درست‌نمایی** پاسخ `v` به facet `f` تحت فرضیهٔ `h`، با مجموعهٔ پاسخ‌های ممکن `C`، با نویز `ε = 0.15`:
  - اگر `h` دربارهٔ `f` پیش‌بینی ندارد: `1/|C|`
  - اگر `v` با پیش‌بینی جور است (مجموعهٔ `M`): `(1−ε)/|M|`
  - در غیر این صورت: `ε/(|C|−|M|)`

  برای facetهای نسخه، `C` از مرزهای بازه‌ها ساخته می‌شود: خودِ هر مرز، کمی پایین‌تر از آن و کمی بالاتر از آن.
- **به‌روزرسانی**: برای هر واقعیت معلوم، `P(h | facts) ∝ P(h) · Π P(fact | h)`.
- **ارزش یک سؤال**: `EIG(f) = H(belief) − Σ_v P(v)·H(belief | v)`، و امتیاز آن `EIG / cost` است. سؤالی که همهٔ فرضیه‌ها جواب یکسانی برایش پیش‌بینی می‌کنند **صفر بیت** ارزش دارد، هر چقدر هم «استاندارد» باشد. به همین دلیل سیستم فهرست ثابتی از مشخصات نمی‌پرسد.

### ۵. سیاست تصمیم (`decision.py`)

| شرط | تصمیم |
|---|---|
| فرضیهٔ اول posterior ≥ 0.60 دارد، دست‌کم 0.30 از دومی (شامل `unlisted_cause`) جلوتر است و شواهدش **strong** است (مستندات، release note یا گفتهٔ نگه‌دارنده) | `propose_answer` (+ حداکثر یک بررسی تأییدی) |
| در غیر این صورت، اگر سؤالی با `score ≥ 0.05` هست | `request_information` با حداکثر دو سؤال برتر |
| هیچ فرضیه‌ای نیست، یا هیچ سؤالی میان فرضیه‌ها فرق نمی‌گذارد | `escalate` + درخواست اطلاعات پایه‌ای که **هنوز گفته نشده** (fallback)، به‌همراه limitations |

فرضیه‌ای که فقط با گزارش‌های مشابهِ کاربران دیگر پشتیبانی می‌شود (**weak**)، حتی با posterior بالا، به‌عنوان پاسخ پیشنهاد نمی‌شود. چون «ارجاع به یک گزارش مشابه به‌تنهایی اثبات نمی‌کند که علت دو مشکل یکسان است».

### رفتار روی مثال صورت پروژه (`examples/`)

| نوبت | آنچه کاربر گفته | تصمیم سیستم |
|---|---|---|
| ۱ | محلی کار می‌کند، روی سرور در بارگذاری می‌ماند، نصب مجدد کمکی نکرد | می‌پرسد آیا reverse proxy هست، و بعد آیا زیرمسیر (sub-path) در کار است. نصب مجدد را تکرار نمی‌کند و فرضیهٔ «محیط خراب» را تضعیف می‌کند |
| ۲ | «nginx جلویش است. کنسول را هم نگاه کردم» | `follow_up`: «گفتید کنسول را دیدید، نتیجه چه بود؟» |
| ۳ | «WebSocket connection to …/_stcore/stream failed» | `propose_answer` → `h_proxy_websocket` |
| — | «هیچ reverse proxy‌ای نیست» | فرضیهٔ proxy عقب می‌افتد و سؤال‌ها به sub-path و health check می‌روند |
| — | بخش ۱-۱ چیزی پیدا نکرده | `escalate` + درخواست متن خطا و محل استقرار (نسخه را چون گفته شده نمی‌پرسد) |

---

## نحوهٔ اتصال به بخش‌های دیگر

### از پایتون

```python
from missing_info import AnalysisInput, AnalyzerConfig, Case, analyze

data = AnalysisInput.model_validate({
    "case": Case.from_github(issue_json, comments_json).model_dump(),
    "evidence_bundle": part1_output,      # dict با کلیدهای evidence و hypotheses
})
report = analyze(data)                    # NextStepReport (pydantic)
report.decision.type                      # DecisionType.REQUEST_INFORMATION
report.next_steps[0].text                 # متن سؤال آماده برای کاربر
payload = report.model_dump(mode="json")  # dict قابل ذخیره در JSON یا SQLite (مسئلهٔ ۲)
```

با LLM:

```python
from pathlib import Path

from missing_info.llm import CachedChatClient, LLMProfiler, OpenAICompatibleClient
from missing_info.profiling import RuleBasedProfiler

client = CachedChatClient(Path("runs/llm_cache.json"), OpenAICompatibleClient.from_env())
report = analyze(data, profilers=[LLMProfiler(client), RuleBasedProfiler()])
```

### برای بخش ۱-۱

اگر خروجی‌تان کمی متفاوت است، کافی است یک adapter کوچک بنویسید که آن را به `EvidenceBundle` تبدیل کند. اعتبارسنجی pydantic ارجاع‌های شکسته و شناسه‌های تکراری را همان‌جا گزارش می‌کند. هر چه `expectations` دقیق‌تری بدهید، سؤال‌ها هدفمندتر می‌شوند.

### برای بخش ۱-۳

- `decision` نوع پاسخ را تعیین می‌کند: راهنما یا مشکل شناخته‌شده، درخواست اطلاعات، یا ارجاع.
- `next_steps[].text` را می‌توان مستقیم در پاسخ کاربر گذاشت.
- `known_facts`، `skipped_probes`، `hypotheses` (با `evidence_ids` برای ارجاع) و `limitations` مستقیماً خلاصهٔ فنی نگه‌دارنده را می‌سازند: محیط، بررسی‌های انجام‌شده، منابع مؤثر و ابهام‌ها.

### برای مسئلهٔ ۲

`analyze` تابعی خالص و بدون حالت است. پس می‌شود بعد از هر پیام جدید کاربر دوباره صدایش زد، و اصلاحیه‌ها خودکار در `superseded` می‌آیند. به همین دلیل می‌تواند مستقیماً یک «ابزار» عامل باشد.

---

## پیکربندی

همهٔ آستانه‌ها در `AnalyzerConfig` (`missing_info/config.py`) هستند:

| پارامتر | پیش‌فرض | معنی |
|---|---|---|
| `observation_noise` | 0.15 | احتمال این‌که مشاهده‌ای با فرضیهٔ درست ناسازگار باشد |
| `unlisted_cause_prior` | 0.20 | سهم «علت فهرست‌نشده» از prior |
| `answer_threshold` | 0.60 | حداقل posterior برای پیشنهاد پاسخ |
| `answer_margin` | 0.30 | حداقل فاصله با فرضیهٔ دوم |
| `min_information_gain` | 0.05 | حداقل امتیاز (بیت به ازای هر واحد هزینه) برای پرسیدن |
| `max_probes` | 2 | حداکثر سؤال در هر نوبت |
| `require_strong_evidence_for_answer` | True | پاسخ فقط با پشتوانهٔ معتبر |

این مقادیر نقطهٔ شروع‌اند و باید **فقط روی ۱۵ پروندهٔ توسعه** کالیبره شوند، نه روی مجموعهٔ آزمون.

---

## توسعه و افزودن قابلیت

برای پوشش یک نوع مشکل جدید، مثلاً مشکلات `st.session_state`:

1. در `facets.py` یک `Facet` تعریف کنید (شناسه، نوع، مقادیر، متن پرسش و هزینه).
2. در `extraction.py` قواعد تشخیص آن را از متن کاربر به `RULES` اضافه کنید. قاعدهٔ خاص‌تر را جلوتر بگذارید.
3. (اختیاری) در `profiling.py` یک `ProfileRule` بگذارید تا فرضیه‌های آن خانواده این facet را پیش‌بینی کنند.
4. برایش آزمون بنویسید: یک نمونهٔ مثبت و یک نمونه که **نباید** حدس زده شود.

بقیهٔ سیستم (امتیازدهی، تصمیم و خروجی) بدون تغییر کار می‌کند.

---

## آزمون‌ها

```bash
.venv/bin/pytest -q
```

۱۰۷ آزمون واحد و سرتاسری این موارد را پوشش می‌دهند:

- قرارداد داده‌ها و اعتبارسنجی
- قواعد استخراج: موارد مثبت، موارد «نباید حدس بزند»، مثال فارسی و انگلیسی صورت پروژه، اصلاح کاربر، نادیده گرفتن نظر نگه‌دارنده
- پروفایلینگ و بازهٔ نسخه
- ریاضیات باور و EIG
- سناریوهای چندنوبتی
- LLM با کلاینت ساختگی (fake) و cache
- CLI

**هیچ آزمونی به شبکه یا کلید API نیاز ندارد.**

---

## ساختار پوشه‌ها

```
missing_info/
  schemas.py      قرارداد ورودی و خروجی (pydantic)
  config.py       آستانه‌ها و پارامترها
  facets.py       کاتالوگ facetها: پرسش‌ها و بررسی‌ها
  expectations.py تطبیق مقدار با پیش‌بینی (شامل بازهٔ نسخه)
  extraction.py   استخراج واقعیت‌های معلوم و کارهای انجام‌شده از گفت‌وگو
  profiling.py    تبدیل فرضیه به پیش‌بینی (bundle، قواعد و پروفایلرهای قابل‌تعویض)
  scoring.py      مدل باور بیزی و بهرهٔ اطلاعاتی
  probes.py       ساخت و رتبه‌بندی سؤال، بررسی و پیگیری، به‌همراه دلیل
  decision.py     سیاست propose / request / escalate
  pipeline.py     analyze(): اتصال همهٔ مراحل
  render.py       گزارش Markdown
  llm.py          پروفایلر LLM اختیاری (متیس)، سقف بودجه و cache ضبط/بازپخش
  cli.py          رابط خط فرمان missing-info
schemas/          JSON Schema ورودی و خروجی (تولیدشده)
examples/         ورودی‌های نمونه + outputs/ (گزارش‌های تولیدشده)
tests/            آزمون‌ها
```

---

## مراحل ساخت (تاریخچهٔ کامیت‌ها)

1. اسکلت پروژه و قرارداد داده‌های ورودی و خروجی
2. کاتالوگ facetها و تطبیق expectationها
3. استخراج قاعده‌محور واقعیت‌ها و کارهای انجام‌شده
4. تبدیل فرضیه به پیش‌بینی‌های قابل‌آزمون
5. مدل باور بیزی و بهرهٔ اطلاعاتی
6. نقل‌قول در سطح جمله و تشخیص «کنسول را دیدم»
7. انتخاب قدم بعدی، سیاست تصمیم و pipeline
8. پشتیبانی از چند پروفایلر به ترتیب اولویت
9. پروفایلر LLM اختیاری با سقف بودجه و cache
10. CLI و گزارش Markdown
11. ورودی‌های نمونه، گزارش‌های تولیدشده و JSON Schema
12. همین README

---

## محدودیت‌ها و کارهای بعدی

- **ارزیابی هنوز انجام نشده.** مجموعهٔ ۳۰ پرونده (۱۵ توسعه و ۱۵ آزمون) کار مشترک تیم است. پیشنهاد معیار برای این بخش:
  - سهم پرونده‌هایی که سؤال اول یکی از «اطلاعات گمشدهٔ» برچسب‌خورده را هدف می‌گیرد
  - نرخ سؤال تکراری یا قبلاً پاسخ‌داده‌شده (هدف: صفر)
  - دقت تصمیم، جداگانه برای پرونده‌های قابل پاسخ، مبهم و نیازمند ارجاع
  - مقایسه با Baseline «پرسیدن فهرست ثابت مشخصات»
- قواعد regex پوشش کامل ندارند. هر چه پیدا نشود نامعلوم می‌ماند؛ نتیجه‌اش احتمالاً یک سؤال اضافه است، نه یک نتیجهٔ غلط. پوشش فارسی فقط در حد مثال صورت پروژه است.
- فرض استقلال مشاهدات در به‌روزرسانی بیزی ساده‌سازی است، مثلاً `reverse_proxy` و `websocket_error_in_console` به هم وابسته‌اند.
- آستانه‌ها فعلاً دستی‌اند. کالیبراسیون یا روش‌های Conformal برای تصمیم میان پاسخ، پرسش و ارجاع یکی از مسیرهای بخش امتیازی است.
- فهرست facetها روی مشکلات اجرا و استقرار، نسخه، مرورگر و cache متمرکز است و برای دامنهٔ نهایی تیم باید گسترش پیدا کند.
- درگاه متیس به‌صورت واقعی تست نشده است (کلید در دسترس نبود). کلاینت استاندارد OpenAI است و `METIS_BASE_URL` قابل تنظیم است.
