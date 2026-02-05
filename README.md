# Multi-Model Opinion Flow 🔄

כלי לקבלת דעות מרובות ממודלי AI מובילים.
כל מודל מקבל את התשובות הקודמות ובונה עליהן - כך נוצר פתרון משודרג!

## 🎯 הרעיון

כשיש בעיה מורכבת ואתה רוצה הרבה דעות:

1. **מודל 1** עונה על השאלה
2. **מודל 2** מקבל את השאלה + תשובת מודל 1 → בונה על זה
3. **מודל 3** מקבל את השאלה + תשובות 1+2 → משדרג עוד
4. וכן הלאה...

לכל מודל יש "כיוון חשיבה" משלו. כשהוא רואה רעיונות של אחרים - הוא מגלה זוויות שלא היה חושב עליהן לבד!

## 📦 מודלים נתמכים

| מודל | חברה | תיאור |
|------|------|-------|
| **Claude** | Anthropic | מודל מוביל, מצוין לניתוח |
| **Gemini** | Google | יכולות multimodal, חלון הקשר גדול |
| **GPT** | OpenAI | המודל הפופולרי ביותר |
| **Mistral** | Mistral AI | מודל אירופאי איכותי |
| **Grok** | xAI | מודל של אילון מאסק |
| **DeepSeek** | DeepSeek | מודל סיני עם reasoning מתקדם |
| **Perplexity** | Perplexity | מיוחד לחיפוש ברשת עם מקורות |

## 🚀 התקנה

```bash
# Clone
git clone https://github.com/amirbiron/architect-agent.git
cd architect-agent

# התקנת תלויות
pip install -r requirements.txt

# הגדרת API keys
cp .env.example .env
# ערוך את .env והוסף את המפתחות שלך
```

## ⚙️ הגדרת API Keys

ערוך את קובץ `.env` והוסף את המפתחות:

```env
# חובה - לפחות אחד
ANTHROPIC_API_KEY=sk-ant-...    # Claude
OPENAI_API_KEY=sk-...           # GPT

# אופציונלי - המודלים הנוספים
GEMINI_API_KEY=AI...
MISTRAL_API_KEY=...
GROK_API_KEY=xai-...
DEEPSEEK_API_KEY=sk-...
PERPLEXITY_API_KEY=pplx-...
```

## 💻 שימוש

### ממשק Web (מומלץ)

```bash
# הפעלת השרת
uvicorn src.api.main:app --reload

# פתח בדפדפן
# http://localhost:8000
```

### CLI

```bash
# מצב אינטראקטיבי
python main.py

# שאלה בודדת
python main.py -q "מה הדרך הטובה ביותר ללמוד Python?"

# בחירת מודלים ספציפיים
python main.py -q "שאלה" -m claude gpt gemini

# שמירה לקובץ
python main.py -q "שאלה" -o output.md

# רשימת מודלים זמינים
python main.py --list
```

## 🌐 ממשק Web

הממשק מאפשר:
- ✅ בחירת מודלים
- ✅ גרירה לשינוי סדר
- ✅ תצוגת תשובות בזמן אמת
- ✅ פורמט Markdown מעוצב
- ✅ העתקה ללוח

## 📁 מבנה הפרויקט

```
├── main.py                 # CLI
├── src/
│   ├── config.py           # הגדרות
│   ├── flow.py             # הזרימה העיקרית
│   ├── models/             # מימוש המודלים
│   │   ├── base.py
│   │   ├── claude.py
│   │   ├── gemini.py
│   │   ├── gpt.py
│   │   ├── mistral.py
│   │   ├── grok.py
│   │   ├── deepseek.py
│   │   └── perplexity.py
│   ├── api/                # FastAPI
│   │   └── main.py
│   └── static/             # ממשק Web
│       └── index.html
├── requirements.txt
└── .env.example
```

## 🔧 API Endpoints

| Method | Endpoint | תיאור |
|--------|----------|-------|
| GET | `/` | ממשק Web |
| GET | `/api/models` | רשימת מודלים וזמינות |
| POST | `/api/ask` | שליחת שאלה (SSE streaming) |
| GET | `/api/health` | בדיקת תקינות |

### דוגמת שימוש ב-API

```bash
# בדיקת מודלים זמינים
curl http://localhost:8000/api/models

# שליחת שאלה
curl -X POST http://localhost:8000/api/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "מה זה Python?", "models": ["claude", "gpt"]}'
```

## 📝 רישיון

MIT

---

נבנה עם ❤️ ו-AI
