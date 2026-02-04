# 🎯 משימה ל-Claude Code: הוספת Multi-Agent Ensemble

## מטרה
להוסיף לפרויקט Architect Agent מערכת Multi-Agent שבה 4 סוכנים (כל אחד מודל אחר) עובדים יחד:
- **Generator** (Claude) - מציע ארכיטקטורה
- **Critic** (GPT) - מבקר ומוצא חורים
- **Cost/Ops** (Gemini) - בודק עלות והיתכנות
- **Synthesizer** (Claude) - ממזג לתוצר סופי

---

## מבנה הריפו הנוכחי

```
architect-agent/
├── src/
│   ├── config.py                    # Settings - כבר יש ANTHROPIC_API_KEY
│   ├── agent/
│   │   ├── state.py                 # ProjectContext + כל המודלים
│   │   ├── graph.py                 # LangGraph workflow + router node
│   │   └── nodes/                   # 8 נודים קיימים
│   │       ├── intake.py
│   │       ├── priority.py
│   │       ├── conflict.py
│   │       ├── deep_dive.py
│   │       ├── pattern.py           # ← להחליף בלוגיקת Multi-Agent
│   │       ├── feasibility.py       # ← להחליף בלוגיקת Multi-Agent
│   │       ├── blueprint.py         # ← להחליף בלוגיקת Multi-Agent
│   │       └── critic.py            # ← להחליף בלוגיקת Multi-Agent
│   ├── knowledge/
│   │   ├── patterns.py              # 6 patterns עם metadata
│   │   └── decision_matrix.py       # מערכת ניקוד דטרמיניסטית
│   ├── llm/
│   │   ├── client.py                # Claude client - צריך להפשיט ל-Protocol
│   │   └── prompts.py               # פרומפטים - צריך להוסיף
│   ├── db/                          # MongoDB - קיים ועובד
│   └── api/                         # FastAPI - קיים ועובד
├── requirements.txt
└── .env.example
```

---

## מה כבר קיים בקוד (לא לשכפל!)

### ב-state.py - שדות tracking כבר קיימים:
```python
# שדות שכבר קיימים - לא להוסיף שוב!
revision_count: int = 0
last_pattern: Optional[str] = None
last_confidence_reason: Optional[str] = None
waiting_for_user: bool = False
```

### ב-graph.py - Router node כבר קיים:
```python
# Router שמחליט מאיפה להתחיל בהתאם ל-state:
# - אם יש blueprint → ממשיך מ-deep_dive
# - אם יש proposed_architecture → ממשיך מ-assess_feasibility
# - אם יש requirements → ממשיך מ-priority
# - אחרת → מתחיל מ-intake
```

### ב-critic.py - לוגיקת loop prevention כבר קיימת:
```python
# 5 כללים למניעת לופים:
# 1. missing_info → waiting_for_user=True, לא חוזרים אחורה
# 2. confidence >= 0.5 → יוצאים עם assumptions
# 3. revision_count >= 2 → מסיימים
# 4. same pattern → לא חוזרים שוב
# 5. max_iterations → יציאה
```

---

## מה צריך לממש

### 1. יצירת src/llm/base.py - Protocol בסיסי (חדש!)

```python
"""
ממשק אחיד לכל ספקי ה-LLM.
כל ה-nodes ישתמשו ב-BaseLLMClient במקום LLMClient.
"""
from abc import ABC, abstractmethod
from typing import TypeVar, Type, Optional

T = TypeVar('T')

class BaseLLMClient(ABC):
    """Protocol אחיד לכל ספקי LLM."""

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7
    ) -> str:
        """יצירת טקסט חופשי."""
        ...

    @abstractmethod
    async def generate_structured(
        self,
        prompt: str,
        response_model: Type[T],
        system_prompt: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7
    ) -> T:
        """יצירת פלט מובנה לפי Pydantic model."""
        ...

    @abstractmethod
    async def generate_with_history(
        self,
        messages: list,
        system_prompt: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7
    ) -> str:
        """יצירת טקסט עם היסטוריית שיחה."""
        ...
```

### 2. הרחבת config.py - הוספת API keys

```python
# להוסיף ל-Settings:
OPENAI_API_KEY: str = ""           # ל-Critic (GPT)
GOOGLE_API_KEY: str = ""           # ל-Cost/Ops (Gemini)

# מודלים ספציפיים לכל סוכן  ### דרוש עדכון מודלים עדכני יותר
GENERATOR_MODEL: str = "claude-sonnet-4-5-20250929"     # Claude
CRITIC_MODEL: str = "gpt-4o"                          # OpenAI
COST_OPS_MODEL: str = "gemini-pro"               # Google
SYNTHESIZER_MODEL: str = "claude-sonnet-4-5-20250929"  # Claude
```

### 3. יצירת src/llm/multi_provider.py - Client לכל הספקים

```python
"""
Client אחיד שתומך ב-3 ספקים ומממש את BaseLLMClient.
"""
from typing import Literal, Type, TypeVar, Optional
import logging

from anthropic import AsyncAnthropic
from openai import AsyncOpenAI
import google.generativeai as genai

from .base import BaseLLMClient
from ..config import settings

logger = logging.getLogger(__name__)
T = TypeVar('T')


class MultiProviderLLM(BaseLLMClient):
    """Unified interface for multiple LLM providers."""

    def __init__(self):
        self._anthropic = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        self._openai = AsyncOpenAI(api_key=settings.OPENAI_API_KEY) if settings.OPENAI_API_KEY else None
        self._gemini_configured = False
        if settings.GOOGLE_API_KEY:
            genai.configure(api_key=settings.GOOGLE_API_KEY)
            self._gemini_configured = True

    async def call(
        self,
        provider: Literal["anthropic", "openai", "google"],
        model: str,
        system_prompt: str,
        user_prompt: str,
        response_model: Optional[Type[T]] = None
    ) -> dict | T:
        """
        קריאה אחידה לכל ספק.

        Args:
            provider: הספק לשימוש
            model: שם המודל
            system_prompt: הוראות מערכת
            user_prompt: הפרומפט של המשתמש
            response_model: Pydantic model לפלט מובנה (אופציונלי)

        Returns:
            dict או Pydantic model
        """
        try:
            if provider == "anthropic":
                return await self._call_anthropic(model, system_prompt, user_prompt, response_model)
            elif provider == "openai":
                return await self._call_openai(model, system_prompt, user_prompt, response_model)
            elif provider == "google":
                return await self._call_google(model, system_prompt, user_prompt, response_model)
            else:
                raise ValueError(f"Unknown provider: {provider}")
        except Exception as e:
            # אם Anthropic נכשל - אין fallback, מעלים את השגיאה
            if provider == "anthropic":
                logger.error(f"Anthropic failed with no fallback: {e}")
                raise
            # אחרת - fallback ל-Claude
            logger.warning(f"{provider} failed: {e}, falling back to Claude")
            return await self._call_anthropic(
                settings.GENERATOR_MODEL,
                system_prompt,
                user_prompt,
                response_model
            )

    async def _call_anthropic(self, model: str, system: str, prompt: str, response_model: Optional[Type[T]]) -> dict | T:
        """קריאה ל-Claude."""
        # מימוש דומה ל-client.py הקיים
        ...

    async def _call_openai(self, model: str, system: str, prompt: str, response_model: Optional[Type[T]]) -> dict | T:
        """קריאה ל-GPT."""
        if not self._openai:
            raise RuntimeError("OpenAI not configured")

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt}
        ]

        if response_model:
            # Structured output עם response_format
            response = await self._openai.beta.chat.completions.parse(
                model=model,
                messages=messages,
                response_format=response_model
            )
            return response.choices[0].message.parsed
        else:
            response = await self._openai.chat.completions.create(
                model=model,
                messages=messages
            )
            return {"content": response.choices[0].message.content}

    async def _call_google(self, model: str, system: str, prompt: str, response_model: Optional[Type[T]]) -> dict | T:
        """קריאה ל-Gemini."""
        if not self._gemini_configured:
            raise RuntimeError("Gemini not configured")

        gemini_model = genai.GenerativeModel(
            model_name=model,
            system_instruction=system
        )

        response = await gemini_model.generate_content_async(prompt)

        if response_model:
            # פרסור JSON לתוך Pydantic
            import json
            data = json.loads(response.text)
            return response_model(**data)
        else:
            return {"content": response.text}

    # מימוש ממשק BaseLLMClient
    async def generate(self, prompt: str, system_prompt: Optional[str] = None, **kwargs) -> str:
        result = await self.call("anthropic", settings.GENERATOR_MODEL, system_prompt or "", prompt)
        return result.get("content", "") if isinstance(result, dict) else str(result)

    async def generate_structured(self, prompt: str, response_model: Type[T], system_prompt: Optional[str] = None, **kwargs) -> T:
        return await self.call("anthropic", settings.GENERATOR_MODEL, system_prompt or "", prompt, response_model)

    async def generate_with_history(self, messages: list, system_prompt: Optional[str] = None, **kwargs) -> str:
        # מימוש עם היסטוריה
        ...
```

### 4. יצירת src/agent/nodes/experts/ - תיקייה חדשה לסוכנים

```
src/agent/nodes/experts/
├── __init__.py
├── generator.py      # Agent 1 - Solution Architect (Claude)
├── critic.py         # Agent 2 - Red Team (GPT)
├── cost_ops.py       # Agent 3 - Feasibility (Gemini)
├── synthesizer.py    # Agent 4 - Blueprint Editor (Claude)
└── schemas.py        # Pydantic schemas לפלט אחיד
```

### 5. schemas.py - פורמט פלט אחיד לכל סוכן

```python
"""
סכימות Pydantic לפלט אחיד מכל הסוכנים.
"""
from typing import List, Optional, Literal
from pydantic import BaseModel, Field


class KeyDecision(BaseModel):
    """החלטה ארכיטקטונית."""
    title: str
    decision: str
    rationale: str
    alternatives_considered: List[str] = []


class TechComponent(BaseModel):
    """רכיב טכנולוגי ב-stack."""
    name: str
    role: str  # מה הוא עושה
    justification: str  # למה בחרנו בו


class Risk(BaseModel):
    """סיכון מזוהה."""
    description: str
    severity: Literal["low", "medium", "high", "critical"]
    mitigation: str
    owner: Optional[str] = None  # מי אחראי לטפל


class Unknown(BaseModel):
    """מידע חסר."""
    question: str
    impact: Literal["low", "medium", "high"]
    default_assumption: Optional[str] = None  # מה נניח אם לא נקבל תשובה


class Issue(BaseModel):
    """בעיה שמצא ה-Critic."""
    description: str
    severity: Literal["minor", "major", "critical"]
    location: str  # איפה בהצעה
    suggested_fix: str


class Fix(BaseModel):
    """תיקון מוצע."""
    issue: str
    fix: str
    effort: Literal["trivial", "small", "medium", "large"]


class ExpertOutput(BaseModel):
    """פלט אחיד מכל סוכן."""
    summary: str = Field(..., description="סיכום ב-2-3 משפטים")
    pattern_recommendation: str = Field(..., description="Pattern מומלץ")
    key_decisions: List[KeyDecision] = Field(default_factory=list, min_length=3, max_length=7)
    tech_stack: List[TechComponent] = Field(default_factory=list)
    risks: List[Risk] = Field(default_factory=list)
    unknowns: List[Unknown] = Field(default_factory=list)
    mermaid_diagram: Optional[str] = None
    cost_band: Literal["low", "medium", "high"] = "medium"
    ops_band: Literal["low", "medium", "high"] = "medium"
    confidence: float = Field(..., ge=0, le=1, description="רמת ביטחון 0-1")


class CriticOutput(ExpertOutput):
    """פלט ספציפי ל-Critic."""
    issues_found: List[Issue] = Field(default_factory=list)
    suggested_fixes: List[Fix] = Field(default_factory=list)
    questions_for_user: List[str] = Field(default_factory=list, description="שאלות שחייב לשאול")
    failure_modes: List[str] = Field(default_factory=list, max_length=5, description="Top 5 failure modes")
    low_confidence_reason: Optional[Literal[
        "missing_info",
        "conflicting_constraints",
        "weak_justification",
        "wrong_pattern",
        "risks_not_mitigated",
        "other"
    ]] = None


class CostOpsOutput(BaseModel):
    """פלט ספציפי ל-Cost/Ops."""
    cost_band: Literal["low", "medium", "high"]
    cost_justification: str
    ops_band: Literal["low", "medium", "high"]
    ops_justification: str
    top_cost_drivers: List[str] = Field(default_factory=list, min_length=3, max_length=7)
    top_ops_pains: List[str] = Field(default_factory=list, min_length=3, max_length=7)
    cheaper_alternatives: List[dict] = Field(default_factory=list, description="[{current, alternative, savings}]")
    risk_reducers: List[str] = Field(default_factory=list, min_length=3, max_length=5)
    team_fit_score: float = Field(..., ge=0, le=1)
    team_fit_issues: List[str] = Field(default_factory=list)


class SynthesizerOutput(BaseModel):
    """פלט סופי מה-Synthesizer."""
    executive_summary: str = Field(..., description="סיכום מנהלים ב-4-8 שורות בעברית")
    final_pattern: str
    final_tech_stack: List[TechComponent]
    final_decisions: List[KeyDecision]
    mermaid_diagram: str
    roadmap: dict = Field(..., description="{phase1: [tasks], phase2: [tasks], ...}")
    adrs: List[dict] = Field(default_factory=list, min_length=3, max_length=6)
    assumptions: List[str] = Field(default_factory=list, min_length=3, max_length=8)
    open_unknowns: List[Unknown] = Field(default_factory=list)
    final_risks: List[Risk] = Field(default_factory=list)
    confidence: float = Field(..., ge=0, le=1)
    dissenting_opinions: List[str] = Field(default_factory=list, description="דעות מיעוט מהסוכנים האחרים")
```

### 6. עדכון state.py - הוספת שדות expert outputs בלבד

```python
# להוסיף ל-ProjectContext (השאר כבר קיים!):

from .nodes.experts.schemas import ExpertOutput, CriticOutput, CostOpsOutput, SynthesizerOutput

class ProjectContext(BaseModel):
    # ... שדות קיימים ...

    # ---- Multi-Agent Outputs ----
    generator_output: Optional[ExpertOutput] = None
    critic_output: Optional[CriticOutput] = None
    cost_ops_output: Optional[CostOpsOutput] = None
    synthesizer_output: Optional[SynthesizerOutput] = None

    # ---- Change Log (לדיבוג) ----
    change_log: List[dict] = Field(default_factory=list)

    def log_change(self, agent: str, change: str):
        """רישום שינוי לדיבוג."""
        self.change_log.append({
            "agent": agent,
            "change": change,
            "iteration": self.iteration_count
        })
```

### 7. עדכון graph.py - זרימה חדשה

```python
"""
הזרימה החדשה עם Multi-Agent:

router ──────────────────────────────────┐
   ↓ (new session)                       │ (returning user)
intake → priority → conflict → deep_dive ←┘
                                    ↓
                              generator
                                    ↓
                         ┌──────────┴──────────┐
                         ↓                     ↓
                      critic              cost_ops
                         └──────────┬──────────┘
                                    ↓
                              synthesizer
                                    ↓
                              final_gate
                                    ↓
                    ┌───────────────┼───────────────┐
                    ↓               ↓               ↓
                   END          ask_user        generator
                                    ↓               ↑
                                router ─────────────┘
"""

from langgraph.graph import StateGraph, END
from typing import Dict, Any

from .state import ProjectContext
from .nodes import intake_node, priority_node, conflict_node, deep_dive_node
from .nodes.experts import generator_node, critic_node, cost_ops_node, synthesizer_node
from ..llm.multi_provider import MultiProviderLLM


def create_architect_graph(llm_client: MultiProviderLLM = None):
    """יצירת הגרף עם תמיכה במולטי-אייג'נט."""

    if llm_client is None:
        llm_client = MultiProviderLLM()

    graph = StateGraph(ProjectContext)

    # ========================================
    # PHASE 1: Information Gathering (קיים)
    # ========================================

    async def _intake(state: ProjectContext) -> Dict[str, Any]:
        ctx, reply = await intake_node(state, llm_client)
        return ctx.model_dump()

    async def _priority(state: ProjectContext) -> Dict[str, Any]:
        ctx, reply = await priority_node(state, llm_client)
        return ctx.model_dump()

    async def _conflict(state: ProjectContext) -> Dict[str, Any]:
        ctx, reply = await conflict_node(state, llm_client)
        return ctx.model_dump()

    async def _deep_dive(state: ProjectContext) -> Dict[str, Any]:
        ctx, reply = await deep_dive_node(state, llm_client)
        return ctx.model_dump()

    # ========================================
    # PHASE 2: Expert Panel (חדש)
    # ========================================

    async def _generator(state: ProjectContext) -> Dict[str, Any]:
        # איפוס waiting_for_user - אם הגענו לכאן, המשתמש כבר הגיב
        state.waiting_for_user = False
        ctx, reply = await generator_node(state, llm_client)
        return ctx.model_dump()

    async def _critic(state: ProjectContext) -> Dict[str, Any]:
        ctx, reply = await critic_node(state, llm_client)
        return ctx.model_dump()

    async def _cost_ops(state: ProjectContext) -> Dict[str, Any]:
        ctx, reply = await cost_ops_node(state, llm_client)
        return ctx.model_dump()

    # ========================================
    # PHASE 3: Synthesis (חדש)
    # ========================================

    async def _synthesizer(state: ProjectContext) -> Dict[str, Any]:
        ctx, reply = await synthesizer_node(state, llm_client)
        return ctx.model_dump()

    async def _final_gate(state: ProjectContext) -> Dict[str, Any]:
        ctx, reply, next_node = await final_gate_node(state)
        ctx_dict = ctx.model_dump()
        ctx_dict["_routing_hint"] = next_node
        return ctx_dict

    # ========================================
    # ROUTER NODE (קיים - לא לשנות!)
    # ========================================

    def _route_entry(state) -> str:
        """Router שמחליט מאיפה להתחיל/להמשיך."""
        if isinstance(state, dict):
            state_dict = state
        else:
            state_dict = state.model_dump()

        # אם יש synthesizer_output וחיכינו למשתמש - חוזרים מ-ask_user
        # הערה: waiting_for_user יאופס ב-generator node (ראה למטה)
        if state_dict.get("synthesizer_output") and state_dict.get("waiting_for_user"):
            return "generator"

        # אם יש generator_output - ממשיכים מ-critic
        if state_dict.get("generator_output"):
            return "critic"

        # אם יש requirements - ממשיכים מ-priority
        if state_dict.get("requirements"):
            return "generator"  # דילוג על intake אם יש כבר requirements

        return "intake"

    # ========================================
    # ADD NODES
    # ========================================

    # Router
    graph.add_node("router", lambda state: state)

    # Phase 1
    graph.add_node("intake", _intake)
    graph.add_node("priority", _priority)
    graph.add_node("conflict", _conflict)
    graph.add_node("deep_dive", _deep_dive)

    # Phase 2
    graph.add_node("generator", _generator)
    graph.add_node("critic", _critic)
    graph.add_node("cost_ops", _cost_ops)

    # Phase 3
    graph.add_node("synthesizer", _synthesizer)
    graph.add_node("final_gate", _final_gate)

    # ========================================
    # SET ENTRY POINT
    # ========================================

    graph.set_entry_point("router")

    # ========================================
    # ADD EDGES
    # ========================================

    # Router edges
    graph.add_conditional_edges(
        "router",
        _route_entry,
        {
            "intake": "intake",
            "generator": "generator",
            "critic": "critic",
        }
    )

    # Phase 1 edges (linear)
    graph.add_edge("intake", "priority")
    graph.add_edge("priority", "conflict")
    graph.add_edge("conflict", "deep_dive")
    graph.add_edge("deep_dive", "generator")

    # Phase 2 edges (generator → parallel critics)
    # הערה: LangGraph תומך ב-parallel execution עם fan-out
    graph.add_edge("generator", "critic")
    graph.add_edge("generator", "cost_ops")

    # After critics → synthesizer
    graph.add_edge("critic", "synthesizer")
    graph.add_edge("cost_ops", "synthesizer")

    # Synthesizer → final gate
    graph.add_edge("synthesizer", "final_gate")

    # Final gate routing
    def _route_from_gate(state) -> str:
        if isinstance(state, dict):
            hint = state.get("_routing_hint")
        else:
            hint = getattr(state, "_routing_hint", None)

        if hint == "ask_user":
            return "end"  # יוצאים ומחכים לתשובה
        elif hint == "generator":
            return "generator"
        else:
            return "end"

    graph.add_conditional_edges(
        "final_gate",
        _route_from_gate,
        {
            "end": END,
            "generator": "generator",
        }
    )

    return graph.compile()
```

---

## פרומפטים לכל סוכן

### Generator (Claude) - src/llm/prompts.py

```python
GENERATOR_SYSTEM_PROMPT = """
אתה Solution Architect בכיר. תפקידך:
1. לקבל ProjectContext עם דרישות, אילוצים, וסדרי עדיפויות
2. להציע ארכיטקטורה מלאה: Pattern + Stack + Diagram + Roadmap + ADRs

כללים:
- תהיה פרקטי: הימנע מטכנולוגיות כבדות אם אין הצדקה
- אל תוסיף דרישות חדשות - אם יש הנחה, סמן אותה
- התחשב ב-priorities: אם velocity חשוב יותר מ-scalability, אל תציע Kubernetes
- החזר JSON בלבד לפי הסכימה ExpertOutput
"""

GENERATOR_USER_PROMPT = """
ProjectContext:
{project_context_json}

Pattern Scores (מהמערכת הדטרמיניסטית):
{scoring_results_json}

משימה:
1. בחר Pattern מתוך ה-shortlist (מנומק)
2. הצע Tech Stack מלא (5-15 רכיבים)
3. צור Mermaid diagram
4. תן Roadmap ב-3 פאזות
5. ציין 3-6 סיכונים + mitigation
6. ציין Unknowns רק אם הן Impact גבוה

החזר JSON לפי סכימת ExpertOutput.
"""
```

### Critic (GPT)

```python
CRITIC_SYSTEM_PROMPT = """
אתה Red Team Architect. אתה לא מתכנן מאפס.
אתה תוקף את ההצעה הקיימת: מוצא כשלים, סיכונים, חוסרים.
המטרה: להפוך את ההצעה לבטוחה יותר, ישימה יותר, וברורה יותר.

כללים:
- אל תציע ארכיטקטורה חדשה - רק תקן את הקיימת
- אל תוסיף Tech Stack חדש בלי הצדקה
- מקד את הביקורת בבעיות אמיתיות, לא ניטפיקינג
"""

CRITIC_USER_PROMPT = """
ProjectContext:
{project_context_json}

Proposal של Generator:
{generator_output_json}

משימה:
1. מצא חורים/כשלים/סתירות (issues_found)
2. תן תיקונים ממוקדים (suggested_fixes) - לא "תבנה מחדש"
3. רשימת שאלות שחייב לשאול את המשתמש (questions_for_user)
4. Top 5 Failure Modes
5. ציין low_confidence_reason אם יש בעיה:
   - missing_info: חסר מידע מהמשתמש
   - conflicting_constraints: סתירה בדרישות
   - weak_justification: ההצעה לא מנומקת מספיק
   - wrong_pattern: צריך pattern אחר
   - risks_not_mitigated: סיכונים לא מטופלים

החזר JSON לפי סכימת CriticOutput.
"""
```

### Cost/Ops (Gemini)

```python
COST_OPS_SYSTEM_PROMPT = """
אתה Cost & Ops Architect. אתה מסתכל רק על:
- עלות (cloud, licenses, development, maintenance)
- מורכבות תפעול (deployment, monitoring, debugging)
- יציבות (failure modes, recovery)
- יכולת צוות (team skills, learning curve)

אתה לא מחפש "הכי יפה", אלא "הכי ישים".
"""

COST_OPS_USER_PROMPT = """
ProjectContext:
{project_context_json}

Proposal של Generator:
{generator_output_json}

Team Info:
- Size: {team_size}
- Experience: {team_experience}
- Current Stack: {current_stack}

משימה:
1. תן cost_band (low/medium/high) + הסבר
2. תן ops_band (low/medium/high) + הסבר
3. top_cost_drivers (3-7 פריטים)
4. top_ops_pains (3-7 נקודות כאב תפעוליות)
5. cheaper_alternatives (אם יש)
6. risk_reducers (3-5 דרכים להקטין סיכון)
7. team_fit_score + issues

החזר JSON לפי סכימת CostOpsOutput.
"""
```

### Synthesizer (Claude)

```python
SYNTHESIZER_SYSTEM_PROMPT = """
אתה Blueprint Editor (עורך ראשי).
אתה מקבל הצעה + ביקורת + בדיקת עלות, ומוציא Blueprint אחד סופי.
אתה אחראי על הכרעה כשיש מחלוקת.

כלל הכרעה: מי שמתאים יותר ל-priorities מנצח.

כללים:
- הבסיס הוא הצעת ה-Generator - לא מתחילים מאפס
- שלב תיקונים מוצדקים מה-Critic
- התחשב בעלות/ops מ-Cost/Ops
- אם יש מחלוקת - ציין אותה ב-dissenting_opinions
"""

SYNTHESIZER_USER_PROMPT = """
ProjectContext:
{project_context_json}

Priorities (לפי סדר חשיבות):
{priorities_json}

Generator Output:
{generator_output_json}

Critic Output:
{critic_output_json}

Cost/Ops Output:
{cost_ops_output_json}

משימה:
1. הפק Blueprint מאוחד - בסיס מ-Generator + תיקונים מוצדקים
2. בסתירה - תעדיף מה שמתאים ל-priorities
3. הוסף Assumptions (3-8) ו-open_unknowns
4. עדכן Mermaid diagram אם נדרש
5. ADRs סופיים (3-6)
6. executive_summary בעברית (4-8 שורות)
7. אם יש דעות מיעוט שלא קיבלת - ציין ב-dissenting_opinions

החזר JSON לפי סכימת SynthesizerOutput.
"""
```

---

## מניעת לופים - חוקים קריטיים

### ב-final_gate_node:

```python
async def final_gate_node(ctx: ProjectContext) -> Tuple[ProjectContext, str, Optional[str]]:
    """
    Gate שמחליט: לסיים, לשאול, או לחזור.

    משתמש בלוגיקה הקיימת מ-critic_node (לא לשכפל!).
    """

    synth = ctx.synthesizer_output
    critic = ctx.critic_output

    if not synth:
        return ctx, "אין פלט מה-Synthesizer", None

    confidence = synth.confidence
    reason = critic.low_confidence_reason if critic else None
    current_pattern = synth.final_pattern

    # כלל 1: מספיק חזרות - יוצאים עם הסתייגויות
    if ctx.revision_count >= 2:
        ctx.log_change("final_gate", "max revisions reached, exiting")
        return ctx, _build_max_revisions_reply(synth), None  # → END

    # כלל 2: אותו pattern - לא חוזרים שוב
    if current_pattern and current_pattern == ctx.last_pattern:
        ctx.log_change("final_gate", "pattern unchanged, exiting")
        return ctx, _build_no_improvement_reply(synth), None  # → END

    # כלל 3: confidence גבוה - יוצאים
    if confidence >= 0.7:
        return ctx, _build_success_reply(synth), None  # → END

    # כלל 4: confidence בינוני - יוצאים עם assumptions
    if confidence >= 0.5:
        return ctx, _build_with_assumptions_reply(synth), None  # → END

    # כלל 5: חסר מידע - שואלים משתמש (לא חוזרים פנימית!)
    if reason == "missing_info":
        questions = critic.questions_for_user if critic else []
        ctx.waiting_for_user = True
        return ctx, _build_questions_reply(questions), "ask_user"

    # כלל 6: בעיה אחרת - מנסים שוב עם שינוי
    ctx.revision_count += 1
    ctx.last_pattern = current_pattern
    ctx.log_change("final_gate", f"revision {ctx.revision_count}, trying again")
    return ctx, _build_retry_reply(synth, reason), "generator"
```

---

## API Keys ב-.env

```bash
# Anthropic (Claude) - Generator + Synthesizer
ANTHROPIC_API_KEY=sk-ant-...

# OpenAI (GPT) - Critic
OPENAI_API_KEY=sk-...

# Google (Gemini) - Cost/Ops
GOOGLE_API_KEY=AIza...

# Model overrides (optional)
GENERATOR_MODEL=claude-sonnet-4-20250514
CRITIC_MODEL=gpt-4o
COST_OPS_MODEL=gemini-1.5-pro
SYNTHESIZER_MODEL=claude-sonnet-4-20250514
```

---

## סדר עבודה מומלץ

1. **src/llm/base.py** - יצירת Protocol/ABC ✨ חדש!
2. **config.py** - הוסף API keys חדשים
3. **src/llm/multi_provider.py** - צור client אחיד (מממש BaseLLMClient)
4. **עדכן type hints** בכל nodes: `LLMClient` → `BaseLLMClient`
5. **src/agent/nodes/experts/schemas.py** - Pydantic models
6. **src/agent/nodes/experts/*.py** - 4 הסוכנים
7. **src/llm/prompts.py** - הוסף פרומפטים
8. **state.py** - הוסף רק expert outputs (השאר כבר קיים!)
9. **graph.py** - עדכן את הזרימה, שמור על router הקיים
10. **בדיקות** - ודא שעובד עם fallback ל-Claude

---

## הערות חשובות

- **Parallel execution**: Generator רץ קודם, אחר כך Critic + Cost/Ops במקביל (LangGraph fan-out)
- **Scoring נשאר**: מערכת הניקוד הדטרמיניסטית ממשיכה לתת shortlist ל-Generator
- **Fallback**: אם ספק אחד נופל, MultiProviderLLM חוזר ל-Claude אוטומטית
- **הזרימה הקיימת**: intake → priority → conflict → deep_dive נשארים כמו שהם
- **Router קיים**: לא לגעת ב-router - הוא כבר תומך בהמשך מנקודות שונות
- **Loop prevention קיים**: הלוגיקה ב-critic_node עוברת ל-final_gate

---

## מה לא לשנות

⚠️ **אזהרה**: הקוד הבא כבר קיים ועובד - לא לשכפל או לדרוס:

- `state.py`: revision_count, last_pattern, waiting_for_user
- `graph.py`: _route_entry, router node
- `critic.py`: לוגיקת loop prevention (להעביר ל-final_gate, לא לשכפל)

---

## לקריאה נוספת

- [מסמך התיכנון הראשוני](https://github.com/amirbiron/architect-agent/blob/8f9b765e7a59986447f640d6bba32aa776521704/MultiAgent'sPlan.md)

בהצלחה! 🚀
