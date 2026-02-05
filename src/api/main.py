"""
Multi-Model Opinion Flow - FastAPI Server
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from pathlib import Path
import asyncio
import json

from ..flow import MultiModelFlow
from ..config import config, get_models_with_status

app = FastAPI(
    title="Multi-Model Opinion Flow",
    description="קבל דעות מרובות ממודלים מובילים",
    version="1.0.0"
)

# CORS - מאפשר גישה מכל מקום בפיתוח
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# נתיב לקבצים סטטיים
STATIC_DIR = Path(__file__).parent.parent / "static"


# ========== Models ==========

class QuestionRequest(BaseModel):
    """בקשה לשאלה"""
    question: str
    models: list[str] | None = None  # אופציונלי - רשימת מודלים בסדר הרצוי


class ModelInfo(BaseModel):
    """מידע על מודל"""
    id: str
    name: str
    available: bool


# ========== Routes ==========

@app.get("/")
async def root():
    """דף הבית - ממשק המשתמש"""
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/models")
async def get_models() -> list[ModelInfo]:
    """מחזיר רשימת כל המודלים וזמינותם"""
    return [
        ModelInfo(id=model_id, name=name, available=available)
        for model_id, name, available in get_models_with_status()
    ]


@app.post("/api/ask")
async def ask_question(request: QuestionRequest):
    """
    שולח שאלה למודלים ומחזיר תשובות ב-streaming.
    כל תשובה נשלחת כ-Server-Sent Event.
    """
    flow = MultiModelFlow(model_order=request.models)
    available = flow.get_available_models()

    if not available:
        raise HTTPException(
            status_code=400,
            detail="אין מודלים זמינים. הגדר API keys."
        )

    async def generate_responses():
        """Generator שמחזיר תשובות כ-SSE"""
        previous_responses: list[tuple[str, str]] = []

        # שליחת רשימת המודלים שישתתפו
        print(f"[API] מתחיל זרימה עם {len(available)} מודלים: {available}")
        yield f"data: {json.dumps({'type': 'start', 'models': available}, ensure_ascii=False)}\n\n"

        for model_name in available:
            try:
                model = flow.models[model_name]
                print(f"[API] מעבד מודל: {model.name}")

                # הודעה שהתחלנו לעבד מודל
                yield f"data: {json.dumps({'type': 'processing', 'model': model.name}, ensure_ascii=False)}\n\n"

                # בניית הפרומפט
                prompt = model._build_chain_prompt(request.question, previous_responses)

                # שליחה למודל
                response = await model.generate(prompt)
                print(f"[API] תשובה מ-{model.name}: success={response.success}, error={response.error}")

                if response.success:
                    previous_responses.append((model.name, response.content))

                # שליחת התשובה
                yield f"data: {json.dumps({'type': 'response', 'model': response.model_name, 'content': response.content, 'success': response.success, 'error': response.error}, ensure_ascii=False)}\n\n"

            except Exception as e:
                print(f"[API] שגיאה במודל {model_name}: {e}")
                yield f"data: {json.dumps({'type': 'response', 'model': model_name, 'content': '', 'success': False, 'error': str(e)}, ensure_ascii=False)}\n\n"

            # השהיה קטנה בין מודלים
            await asyncio.sleep(0.1)

        # סיום
        print(f"[API] זרימה הסתיימה")
        yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        generate_responses(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive"
        }
    )


@app.get("/api/health")
async def health():
    """בדיקת תקינות"""
    available = config.get_available_models()
    return {
        "status": "ok",
        "available_models": len(available),
        "models": available
    }


# Mount static files (CSS, JS, etc.)
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
