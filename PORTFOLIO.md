---
# Portfolio – Multi-Model Opinion Flow

name: "Multi-Model Opinion Flow"
repo: "https://github.com/amirbiron/multi-model-flow"
status: "פעיל"

one_liner: "כלי לקבלת דעות מרובות ממודלי AI מובילים – כל מודל רואה את התשובות הקודמות ובונה עליהן"

stack:
  - Python 3
  - FastAPI
  - Uvicorn
  - Anthropic SDK (Claude)
  - OpenAI SDK (GPT, Grok, Perplexity)
  - Google Generative AI SDK (Gemini)
  - Mistral AI SDK
  - Vanilla JavaScript
  - marked.js
  - Server-Sent Events (SSE)

key_features:
  - זרימה סדרתית – כל מודל מקבל את התשובות של המודלים הקודמים
  - "6 מודלים נתמכים: Claude, GPT, Gemini, Mistral, Grok, Perplexity"
  - ממשק Web עם Drag-and-Drop לשינוי סדר מודלים
  - Streaming בזמן אמת (SSE)
  - העתקת תשובות בודדות או כולן (Markdown)
  - מצב CLI עם אינטראקטיבי ושאלה בודדת
  - תמיכה RTL (עברית)
  - ערכת צבעים כהה

architecture:
  summary: |
    Backend FastAPI עם endpoint SSE לסטרימינג תשובות.
    Frontend vanilla JS עם ממשק RTL.
    כל מודל AI מיוצג כמחלקה עצמאית (BaseModel) עם אינטגרציה ל-SDK הספציפי.
    Flow engine מפעיל מודלים בסדר שנבחר, מעביר הקשר מצטבר.
  entry_points:
    - main.py – CLI entry point
    - src/api/main.py – FastAPI server
    - src/flow.py – לוגיקת הזרימה
    - src/static/index.html – ממשק Web

demo:
  live_url: "" # TODO: בדוק ידנית (deployed on Render)
  video_url: "" # TODO: בדוק ידנית

setup:
  quickstart: |
    1. git clone <repo-url> && cd multi-model-flow
    2. pip install -r requirements.txt
    3. cp .env.example .env && # מלא API keys
    4. uvicorn src.api.main:app --reload
    5. פתח http://localhost:8000

your_role: "פיתוח מלא – ארכיטקטורה, אינטגרציה ל-6 מודלי AI, ממשק Web, CLI, deployment"

tradeoffs:
  - זרימה סדרתית (לא מקבילית) – כל מודל חייב לחכות לקודם, מה שמאט אך מאפשר העשרה
  - Frontend ב-vanilla JS – פשוט ומהיר, ללא framework
  - OpenAI SDK משותף לכמה ספקים (Grok, Perplexity) דרך base_url שונה

metrics: "" # TODO: בדוק ידנית

faq:
  - q: "צריך מפתחות API לכל 6 המודלים?"
    a: "לא – רק מודלים שיש להם מפתח API מוגדר ב-.env יופעלו. השאר מושבתים אוטומטית."
  - q: "אפשר לשנות את סדר המודלים?"
    a: "כן – בממשק Web אפשר לגרור ולשחרר כדי לשנות סדר, ובCLI עם הדגל -m."
---
