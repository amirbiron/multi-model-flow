# 🏗️ Architect Agent

סוכן AI מבוסס **LangGraph** לתכנון ארכיטקטורת תוכנה.

## 🎯 מה זה?

Architect Agent הוא סוכן שמשלב **לוגיקה דטרמיניסטית** (מערכת ניקוד) עם **LLM** (Claude) כדי:

- לנתח דרישות פרויקט דרך שיחה אינטראקטיבית
- לזהות קונפליקטים בין דרישות ולהציע פשרות
- לבחור Pattern ארכיטקטוני מתאים עם ניקוד שקוף
- להמליץ על Tech Stack
- לייצר Blueprint מקצועי עם Mermaid diagrams ו-ADRs

## 🔄 זרימת העבודה

```
Intake → Priority → Conflict → Deep Dive → Pattern → Feasibility → Blueprint → Critic
   ↑                                                                              ↓
   └──────────────────── (אם confidence < 0.7) ────────────────────────────────────┘
```

## 🚀 התקנה

### דרישות
- Python 3.11+
- MongoDB (Atlas או local)
- מפתח API של Anthropic

### שלבים

```bash
# Clone
git clone <repo-url>
cd architect-agent

# Virtual environment
python -m venv venv
source venv/bin/activate  # או venv\Scripts\activate ב-Windows

# Dependencies
pip install -r requirements.txt

# Environment
cp .env.example .env
# ערוך את .env עם ה-credentials שלך

# Run
uvicorn src.api.main:app --reload
```

## 📡 API Endpoints

| Method | Endpoint | תיאור |
|--------|----------|-------|
| POST | `/api/v1/sessions` | יצירת session חדש |
| GET | `/api/v1/sessions/{id}` | פרטי session |
| POST | `/api/v1/sessions/{id}/chat` | המשך שיחה |
| GET | `/api/v1/sessions/{id}/blueprint` | קבלת ה-Blueprint |
| GET | `/api/v1/patterns` | רשימת Patterns זמינים |

### דוגמה

```bash
# יצירת session חדש
curl -X POST http://localhost:8000/api/v1/sessions \
  -H "Content-Type: application/json" \
  -d '{"message": "אני רוצה לבנות מערכת e-commerce עם 100K משתמשים"}'

# המשך שיחה
curl -X POST http://localhost:8000/api/v1/sessions/{session_id}/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "התקציב שלי $2000 לחודש"}'
```

## 🧠 מערכת הניקוד

הסוכן משתמש במערכת ניקוד דטרמיניסטית:

```
Base Score = Σ (Pattern_Score[criterion] × User_Weight[criterion])

Final Score = Base Score + Constraint_Adjustments
```

### קריטריונים
- Time to Market (0-100)
- Cost (0-100)
- Scale (0-100)
- Reliability (0-100)
- Security (0-100)

### פרופילים מוכנים
- `MVP_FAST` - מהירות מעל הכל
- `COST_FIRST` - חיסכון בעלויות
- `SCALE_FIRST` - בנייה לסקייל
- `SECURITY_FIRST` - אבטחה קודמת

## 📁 מבנה הפרויקט

```
architect-agent/
├── src/
│   ├── agent/
│   │   ├── nodes/          # כל ה-Nodes
│   │   ├── state.py        # ProjectContext
│   │   └── graph.py        # LangGraph definition
│   ├── api/
│   │   ├── main.py         # FastAPI app
│   │   └── routes.py       # Endpoints
│   ├── db/
│   │   ├── mongodb.py      # Client
│   │   └── repositories.py # Data access
│   ├── llm/
│   │   ├── client.py       # Claude wrapper
│   │   └── prompts.py      # System prompts
│   ├── knowledge/
│   │   ├── patterns.py     # Pattern definitions
│   │   └── decision_matrix.py  # Scoring logic
│   └── config.py
├── tests/
├── requirements.txt
├── Dockerfile
├── render.yaml
└── .env.example
```

## 🚢 פריסה ב-Render

```bash
# עם render CLI
render blueprint launch

# או ידנית:
# 1. צור Web Service חדש
# 2. חבר ל-repo
# 3. הגדר environment variables
# 4. Deploy!
```

## 🔧 Environment Variables

| משתנה | תיאור | חובה |
|-------|-------|------|
| `MONGODB_URI` | Connection string | ✅ |
| `ANTHROPIC_API_KEY` | מפתח Claude API | ✅ |
| `MONGODB_DB_NAME` | שם ה-database | ❌ |
| `MAX_ITERATIONS` | מקסימום איטרציות | ❌ |
| `MIN_CONFIDENCE` | סף ביטחון מינימלי | ❌ |

## 🧪 טסטים

```bash
pytest tests/ -v
```

## 📄 License

MIT

---

נבנה עם ❤️ ו-LangGraph
