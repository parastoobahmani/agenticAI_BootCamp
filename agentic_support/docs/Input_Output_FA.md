# ورودی و خروجی پروژهٔ سادهٔ LangChain

این خروجی‌ها از اجرای واقعی برنامه در حالت `--demo` گرفته شده‌اند. حلقهٔ LangChain، ابزارها، SQLite و توقف انسانی واقعی‌اند؛ مدلِ انتخاب‌کنندهٔ ابزار جعلی است و هیچ API بیرونی استفاده نشده است.

در اجرای واقعی، `--demo` را حذف کنید و `.env` را تکمیل کنید. انتخاب ابزارها و متن پاسخ ممکن است متفاوت باشد. مقادیر شناسه‌ها در هر پایگاه دادهٔ تازه از ابتدا شروع می‌شوند.

برای تکرار مثال ابتدا نصب را طبق README انجام دهید. فرمان‌ها را در پوشهٔ پروژه اجرا کنید. در Windows PowerShell آرگومان JSON را داخل کوتیشن تکی قرار دهید. فایل کامل خروجی بدون خلاصه‌سازی در `reports/cli_input_output.json` است.

## ۱. ایجاد پروندهٔ نمایشی

```text
python main.py init-demo
```

خروجی ثبت‌شده:

```text
{
  "id": "demo",
  "title": "Streamlit app stuck loading behind nginx",
  "body": "Designed demo: the page keeps loading after deployment. The cause is unknown.",
  "facts": {},
  "checks": [],
  "history": [],
  "sources": [],
  "unknowns": [],
  "summary": {},
  "comments": [],
  "state": "open",
  "labels": [],
  "revision": 0,
  "turn": 0
}
```

## ۲. انتخاب ابزارها و توقف برای تأیید

```text
python main.py --demo run demo
```

خروجی ثبت‌شده:

```text
MODE: DEMO - fake model, NO API
[TOOL] read_case
[TOOL] search_docs
[TOOL] draft_reply
[TOOL] apply_change
{
  "waiting_for_human": [
    {
      "case_id": "demo",
      "proposal_id": 1,
      "revision": 0,
      "hash": "fc518810baea82fe37d07bd51ed86ae7b87cde30740c1668684cac8c08479d89",
      "payload": {
        "comment": "نسخهٔ Streamlit محیطی که خطا دارد چیست؟\nبرای مقایسه با مستندات و تغییرات نسخه‌ها لازم است."
      },
      "choices": [
        "approve",
        "edit",
        "reject"
      ]
    }
  ],
  "published": false
}
{
  "api_totals_all_live_runs": {
    "attempts": 0,
    "successful_responses": 0,
    "input_tokens": 0,
    "output_tokens": 0,
    "accounted_usd": 0
  }
}
```

## ۳. ویرایش انسانی؛ هنوز منتشر نشده

```text
python main.py --demo review demo
```

ورودی اپراتور پس از نمایش پیشنهاد:

```text
edit
{"comment": "لطفاً نسخهٔ Streamlit محیط دارای خطا را ارسال کنید؛ مقایسهٔ نسخه‌ها به آن وابسته است."}
```

خروجی ثبت‌شده:

```text
MODE: DEMO - fake model, NO API
{
  "waiting_for_human": [
    {
      "case_id": "demo",
      "proposal_id": 1,
      "revision": 0,
      "hash": "fc518810baea82fe37d07bd51ed86ae7b87cde30740c1668684cac8c08479d89",
      "payload": {
        "comment": "نسخهٔ Streamlit محیطی که خطا دارد چیست؟\nبرای مقایسه با مستندات و تغییرات نسخه‌ها لازم است."
      },
      "choices": [
        "approve",
        "edit",
        "reject"
      ]
    }
  ]
}
approve / edit / reject: New payload JSON (not approved yet): [TOOL] read_case
[TOOL] search_docs
[TOOL] draft_reply
[TOOL] apply_change
{
  "waiting_for_human": [
    {
      "case_id": "demo",
      "proposal_id": 2,
      "revision": 0,
      "hash": "ddd6d54d1d3809d19b0dd551bad8dd195ad76e7c553005a12530af91de0928f8",
      "payload": {
        "comment": "لطفاً نسخهٔ Streamlit محیط دارای خطا را ارسال کنید؛ مقایسهٔ نسخه‌ها به آن وابسته است."
      },
      "choices": [
        "approve",
        "edit",
        "reject"
      ]
    }
  ],
  "published": false
}
{
  "api_totals_all_live_runs": {
    "attempts": 0,
    "successful_responses": 0,
    "input_tokens": 0,
    "output_tokens": 0,
    "accounted_usd": 0
  }
}
```

## ۴. تأیید متن ویرایش‌شده و ثبت یک نظر

```text
python main.py --demo review demo
```

ورودی اپراتور پس از نمایش پیشنهاد:

```text
approve
```

خروجی ثبت‌شده:

```text
MODE: DEMO - fake model, NO API
{
  "waiting_for_human": [
    {
      "case_id": "demo",
      "proposal_id": 2,
      "revision": 0,
      "hash": "ddd6d54d1d3809d19b0dd551bad8dd195ad76e7c553005a12530af91de0928f8",
      "payload": {
        "comment": "لطفاً نسخهٔ Streamlit محیط دارای خطا را ارسال کنید؛ مقایسهٔ نسخه‌ها به آن وابسته است."
      },
      "choices": [
        "approve",
        "edit",
        "reject"
      ]
    }
  ]
}
approve / edit / reject: [TOOL] read_case
[TOOL] search_docs
[TOOL] draft_reply
[TOOL] apply_change
DEMO: نتیجهٔ ابزار ثبت شد: {"applied": true, "case_id": "demo", "proposal_id": 2, "state": "open", "comment_count": 1}
{
  "api_totals_all_live_runs": {
    "attempts": 0,
    "successful_responses": 0,
    "input_tokens": 0,
    "output_tokens": 0,
    "accounted_usd": 0
  }
}
```

## ۵. پاسخ کاربر در نوبت بعد

```text
python main.py update demo --message 'نسخهٔ محیط خطادار 1.50.0 است.' --facts '{"streamlit_version": "1.50.0"}'
```

بخش مرتبط خروجی (منابع طولانی اینجا نمایش داده نشده‌اند):

```text
{
  "id": "demo",
  "facts": {
    "streamlit_version": "1.50.0"
  },
  "history": [
    {
      "message": "نسخهٔ محیط خطادار 1.50.0 است.",
      "facts": {
        "streamlit_version": "1.50.0"
      },
      "check": null
    }
  ],
  "comments": [
    {
      "body": "لطفاً نسخهٔ Streamlit محیط دارای خطا را ارسال کنید؛ مقایسهٔ نسخه‌ها به آن وابسته است.",
      "proposal_id": 2
    }
  ],
  "revision": 2,
  "turn": 1
}
```

## ۶. سؤال بعدی با توجه به پاسخ قبلی

```text
python main.py --demo run demo
```

خروجی ثبت‌شده:

```text
MODE: DEMO - fake model, NO API
[TOOL] read_case
[TOOL] search_docs
[TOOL] draft_reply
[TOOL] apply_change
{
  "waiting_for_human": [
    {
      "case_id": "demo",
      "proposal_id": 3,
      "revision": 2,
      "hash": "cd314fd3125ef82af0098a48bc41169d322ba0c554bcbaf9c473bf97d5760024",
      "payload": {
        "comment": "همین برنامه در محیط محلی هم مشکل دارد یا فقط روی سرور؟\nپاسخ، تفاوت محیط استقرار و رفتار برنامه را جدا می‌کند."
      },
      "choices": [
        "approve",
        "edit",
        "reject"
      ]
    }
  ],
  "published": false
}
{
  "api_totals_all_live_runs": {
    "attempts": 0,
    "successful_responses": 0,
    "input_tokens": 0,
    "output_tokens": 0,
    "accounted_usd": 0
  }
}
```

## ۷. رد پیشنهاد دوم؛ نظر دیگری ثبت نمی‌شود

```text
python main.py --demo review demo
```

ورودی اپراتور پس از نمایش پیشنهاد:

```text
reject
```

خروجی ثبت‌شده:

```text
MODE: DEMO - fake model, NO API
{
  "waiting_for_human": [
    {
      "case_id": "demo",
      "proposal_id": 3,
      "revision": 2,
      "hash": "cd314fd3125ef82af0098a48bc41169d322ba0c554bcbaf9c473bf97d5760024",
      "payload": {
        "comment": "همین برنامه در محیط محلی هم مشکل دارد یا فقط روی سرور؟\nپاسخ، تفاوت محیط استقرار و رفتار برنامه را جدا می‌کند."
      },
      "choices": [
        "approve",
        "edit",
        "reject"
      ]
    }
  ]
}
approve / edit / reject: [TOOL] read_case
[TOOL] search_docs
[TOOL] draft_reply
[TOOL] apply_change
DEMO: نتیجهٔ ابزار ثبت شد: {"status": "rejected", "applied": false}
{
  "api_totals_all_live_runs": {
    "attempts": 0,
    "successful_responses": 0,
    "input_tokens": 0,
    "output_tokens": 0,
    "accounted_usd": 0
  }
}
```

## ۸. مشاهدهٔ رخدادهای ثبت‌شده

```text
python main.py audit demo
```

خروجی ثبت‌شده:

```text
[
  {
    "id": 1,
    "case_id": "demo",
    "event": "created",
    "detail": "{}",
    "at": "2026-10-07 15:33:35"
  },
  {
    "id": 2,
    "case_id": "demo",
    "event": "proposed",
    "detail": "{\"proposal_id\": 1}",
    "at": "2026-10-07 15:33:36"
  },
  {
    "id": 3,
    "case_id": "demo",
    "event": "proposed",
    "detail": "{\"proposal_id\": 2}",
    "at": "2026-10-07 15:33:38"
  },
  {
    "id": 4,
    "case_id": "demo",
    "event": "human_approved",
    "detail": "{\"proposal_id\": 2}",
    "at": "2026-10-07 15:33:39"
  },
  {
    "id": 5,
    "case_id": "demo",
    "event": "executed",
    "detail": "{\"applied\": true, \"case_id\": \"demo\", \"comment_count\": 1, \"proposal_id\": 2, \"state\": \"open\"}",
    "at": "2026-10-07 15:33:39"
  },
  {
    "id": 6,
    "case_id": "demo",
    "event": "updated",
    "detail": "{\"fields\": [\"streamlit_version\"], \"turn\": 1}",
    "at": "2026-10-07 15:33:40"
  },
  {
    "id": 7,
    "case_id": "demo",
    "event": "proposed",
    "detail": "{\"proposal_id\": 3}",
    "at": "2026-10-07 15:33:41"
  },
  {
    "id": 8,
    "case_id": "demo",
    "event": "human_rejected",
    "detail": "{\"proposal_id\": 3}",
    "at": "2026-10-07 15:33:42"
  }
]
```

## ۹. مشاهدهٔ تعداد درخواست واقعی API

```text
python main.py cost
```

خروجی ثبت‌شده:

```text
{
  "attempts": 0,
  "successful_responses": 0,
  "input_tokens": 0,
  "output_tokens": 0,
  "accounted_usd": 0
}
```

## چگونه بفهمیم API من استفاده شده است؟

`MODE: LIVE` فقط حالت اجرا را مشخص می‌کند. وجود `[API] attempt=...` نشان می‌دهد تلاش ثبت شده، و `[API] response_received=...` دریافت پاسخ را نشان می‌دهد. مقدار `successful_responses` در فرمان `cost` پاسخ‌های موفق را می‌شمارد. مصرف اعلام‌شده توسط سرویس در `input_tokens` و `output_tokens` ذخیره می‌شود. برای تطبیق صورتحساب نهایی، داشبورد همان ارائه‌دهنده را هم بررسی کنید.

در حالت DEMO همهٔ فراخوانی‌های مدل جعلی‌اند. این فایل نشان می‌دهد در پایان مثال فقط یک نظر تأییدشده وجود دارد؛ رد پیشنهاد دوم چیزی به نظرات اضافه نکرده است. پیشنهاد تازه بعد از دریافت نسخه، دربارهٔ محل بروز مشکل می‌پرسد و سؤال نسخه را تکرار نمی‌کند.

تغییر وضعیت و برچسب نیز همین مسیر را دارد: `draft_status` یا `draft_labels` پیشنهاد می‌سازند و `apply_change` پیش از تغییر، منتظر تصمیم انسان می‌ماند. نمونهٔ اجرایی آن در آزمون `test_status_and_labels_need_human` موجود است.