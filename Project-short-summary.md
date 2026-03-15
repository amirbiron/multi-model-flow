# Multi-Model Opinion Flow

**ריפו:** [amirbiron/multi-model-flow](https://github.com/amirbiron/multi-model-flow)
**סטטוס:** פעיל

כלי לקבלת דעות מרובות ממודלי AI מובילים – כל מודל רואה את התשובות הקודמות ובונה עליהן בפרספקטיבה ייחודית.

## פיצ'רים מרכזיים
- 9 מודלי AI נתמכים: Claude, GPT, Gemini, Mistral, Grok, DeepSeek, Perplexity, Qwen, Manus
- זרימה סדרתית עם prompt chaining – כל מודל מעשיר את ההקשר
- Streaming בזמן אמת (SSE) עם ממשק Web אינטראקטיבי
- Drag-and-Drop לשינוי סדר מודלים
- מצב CLI אינטראקטיבי ושאלה בודדת
- תמיכה RTL מלאה (עברית)

## Tech Stack
Python, FastAPI, Anthropic SDK, OpenAI SDK, Google Generative AI, Mistral SDK, Vanilla JS, SSE

## לינקים
- Live / Demo: <!-- TODO: בדוק ידנית -->
- Docs: README בריפו

## מה עשיתי
פיתוח מלא מאפס – תכנון ארכיטקטורת Flow Engine, אינטגרציה ל-9 ספקי AI שונים, ממשק Web עם streaming, CLI, ו-deployment ל-Render.
