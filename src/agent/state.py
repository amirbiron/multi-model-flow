"""
Architect Agent - State Models
===============================
Pydantic models defining the agent's state and data structures.
ProjectContext is the central state that flows through all nodes.
"""
from typing import List, Dict, Optional, Literal, Any
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum


# ============================================================
# ENUMS
# ============================================================

class Priority(str, Enum):
    """Priority levels for requirements and constraints."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class DecisionProfile(str, Enum):
    """Pre-defined decision profiles for quick prioritization."""
    MVP_FAST = "mvp_fast"          # Speed above all
    COST_FIRST = "cost_first"      # Cost optimization
    SCALE_FIRST = "scale_first"    # Future scalability
    SECURITY_FIRST = "security_first"  # Security & compliance


class CostBand(str, Enum):
    """Cost estimation bands."""
    LOW = "low"        # Up to $500/month
    MEDIUM = "medium"  # $500-$5000/month
    HIGH = "high"      # Above $5000/month


class ArchitecturePattern(str, Enum):
    """Supported architectural patterns."""
    MONOLITH = "monolith"
    MODULAR_MONOLITH = "modular_monolith"
    MICROSERVICES = "microservices"
    SERVERLESS = "serverless"
    EVENT_DRIVEN = "event_driven"
    CQRS = "cqrs"


# ============================================================
# DATA MODELS
# ============================================================

class Requirement(BaseModel):
    """A single project requirement."""
    category: Literal["functional", "non_functional"]
    description: str
    priority: Priority = Priority.MEDIUM
    value: Optional[str] = None  # e.g., "100k users", "99.9% uptime"
    source: str = "user"  # Where the requirement came from


class Constraint(BaseModel):
    """A project constraint or limitation."""
    type: Literal["technical", "budget", "timeline", "compliance", "team"]
    description: str
    severity: Priority = Priority.MEDIUM


class Conflict(BaseModel):
    """A detected conflict between requirements."""
    requirements: List[str]  # Descriptions of conflicting requirements
    explanation: str         # Why it's a conflict
    compromises: List[str]   # 2-3 possible compromise paths
    resolved: bool = False
    chosen_compromise: Optional[str] = None


class PriorityRanking(BaseModel):
    """User's priority ranking (1-5 scale)."""
    time_to_market: int = Field(ge=1, le=5, default=3)
    cost: int = Field(ge=1, le=5, default=3)
    scale: int = Field(ge=1, le=5, default=3)
    reliability: int = Field(ge=1, le=5, default=3)
    security: int = Field(ge=1, le=5, default=3)

    def to_weights(self) -> Dict[str, float]:
        """Convert rankings to normalized weights (0-1)."""
        total = self.time_to_market + self.cost + self.scale + self.reliability + self.security
        return {
            "time_to_market": self.time_to_market / total,
            "cost": self.cost / total,
            "scale": self.scale / total,
            "reliability": self.reliability / total,
            "security": self.security / total
        }


class ArchitecturalDecision(BaseModel):
    """A proposed architectural decision with scoring."""
    pattern: str
    justification: str
    trade_offs: List[str]
    alternatives_considered: List[str] = Field(default_factory=list)
    score: float = Field(ge=0, le=100, default=0.0)


class TechStackComponent(BaseModel):
    """A technology recommendation for a specific layer."""
    layer: Literal[
        "frontend", "backend", "database", "cache",
        "messaging", "auth", "ci_cd", "monitoring", "cloud"
    ]
    technology: str
    reason: str  # נשאר לתאימות אחורה
    justified_by: Optional[str] = None  # REQUIREMENT/NFR/CONSTRAINT/BASELINE_ENTERPRISE
    classification: Optional[Literal[
        "REQUIRED", "BASELINE_ENTERPRISE", "OPTIONAL", "FUTURE"
    ]] = None
    alternatives: List[str] = Field(default_factory=list)


class FeasibilityAssessment(BaseModel):
    """Feasibility analysis results."""
    cost_band: CostBand
    ops_complexity: CostBand
    cost_drivers: List[str]      # What increases cost
    cost_reducers: List[str]     # What reduces cost
    team_fit: bool               # Does it match team capabilities?
    time_estimate: str           # Rough timeline
    risks: List[str] = Field(default_factory=list)


class ADR(BaseModel):
    """Architecture Decision Record."""
    id: str                      # e.g., "ADR-001"
    title: str
    context: str
    decision: str
    justified_by: Optional[str] = None  # REQUIREMENT/NFR/CONSTRAINT/BASELINE_ENTERPRISE
    consequences: List[str]
    alternatives_considered: List[str] = Field(default_factory=list)


class Blueprint(BaseModel):
    """Final output - the architecture blueprint document."""
    executive_summary: str
    mermaid_diagram: str
    adrs: List[ADR]
    roadmap: Dict[str, List[str]]  # phase -> tasks
    next_steps: List[str]
    assumptions: List[str]
    unknowns: List[str]


# ============================================================
# MAIN STATE MODEL
# ============================================================

class ProjectContext(BaseModel):
    """
    The central state of the agent.
    All nodes read from and write to this model.
    This is the "single source of truth" throughout the workflow.
    """
    # ---- Identifiers ----
    session_id: str
    project_name: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # ---- Requirements & Constraints ----
    initial_summary: Optional[str] = None
    requirements: List[Requirement] = Field(default_factory=list)
    constraints: List[Constraint] = Field(default_factory=list)

    # ---- Priorities ----
    decision_profile: Optional[DecisionProfile] = None
    priority_ranking: Optional[PriorityRanking] = None

    # ---- Conflicts ----
    conflicts: List[Conflict] = Field(default_factory=list)

    # ---- Architectural Decisions ----
    proposed_architecture: Optional[ArchitecturalDecision] = None
    shortlist: List[ArchitecturalDecision] = Field(default_factory=list)
    tech_stack: List[TechStackComponent] = Field(default_factory=list)
    feasibility: Optional[FeasibilityAssessment] = None

    # ---- Output ----
    blueprint: Optional[Blueprint] = None

    # ---- Workflow Management ----
    conversation_history: List[Dict[str, Any]] = Field(default_factory=list)
    current_node: str = "intake"
    open_questions: List[str] = Field(default_factory=list)
    confidence_score: float = 0.0
    iteration_count: int = 0
    max_iterations: int = 5

    # ---- Revision Tracking (למניעת לופים) ----
    revision_count: int = 0  # כמה פעמים חזרנו לאחור
    last_pattern: Optional[str] = None  # ה-pattern האחרון שנבחר
    last_confidence_reason: Optional[str] = None  # סיבת confidence נמוך אחרונה

    # ---- Facts & Questions (למניעת לופים ומעקב מידע) ----
    facts: Dict[str, Any] = Field(default_factory=dict)  # עובדות שנאספו מהמשתמש
    asked_questions: List[str] = Field(default_factory=list)  # שאלות שכבר נשאלו
    info_version: int = 0  # גרסת המידע - מתקדם בכל פעם שיש מידע חדש
    last_info_version_used: int = 0  # גרסת המידע האחרונה שבה רצו המומחים

    # ---- Forced Pattern (לאחר swap_option) ----
    forced_pattern: Optional[str] = None  # אם נקבע, ה-Generator חייב לבחור בזה

    # ---- Internal flags ----
    waiting_for_user: bool = False
    error_message: Optional[str] = None
    # הערה: _routing_hint מועבר דרך dict ולא דרך model (ראה graph.py שורה 89)

    def add_message(self, role: str, content: str) -> None:
        """Add a message to conversation history."""
        self.conversation_history.append({
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow().isoformat(),
            "node": self.current_node
        })
        self.updated_at = datetime.utcnow()

    def get_recent_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get the most recent messages from history."""
        return self.conversation_history[-limit:]

    def is_done(self) -> bool:
        """Check if the agent has completed its task."""
        return (
            self.blueprint is not None and
            self.confidence_score >= 0.7 and
            len(self.blueprint.adrs) >= 3
        )

    def has_unresolved_conflicts(self) -> bool:
        """Check for unresolved conflicts."""
        return any(not c.resolved for c in self.conflicts)

    def add_fact(self, key: str, value: Any) -> None:
        """הוספת עובדה חדשה ועדכון גרסת המידע."""
        self.facts[key] = value
        self.info_version += 1
        self.updated_at = datetime.utcnow()

    def add_requirement(self, requirement: "Requirement") -> None:
        """הוספת דרישה חדשה ועדכון גרסת המידע."""
        self.requirements.append(requirement)
        self.info_version += 1
        self.updated_at = datetime.utcnow()

    def add_constraint(self, constraint: "Constraint") -> None:
        """הוספת אילוץ חדש ועדכון גרסת המידע."""
        self.constraints.append(constraint)
        self.info_version += 1
        self.updated_at = datetime.utcnow()

    def bump_info_version(self) -> None:
        """העלאת גרסת המידע - לשימוש כשיש עדכון משמעותי אחר."""
        self.info_version += 1
        self.updated_at = datetime.utcnow()

    def add_asked_question(self, question: str) -> None:
        """הוספת שאלה לרשימת השאלות שכבר נשאלו."""
        if question not in self.asked_questions:
            self.asked_questions.append(question)

    def has_new_info(self) -> bool:
        """בודק אם יש מידע חדש מאז הריצה האחרונה."""
        return self.info_version > self.last_info_version_used

    def mark_info_used(self) -> None:
        """מסמן שהמידע הנוכחי נוצל."""
        self.last_info_version_used = self.info_version

    def get_priority_weights(self) -> Dict[str, float]:
        """Get priority weights from ranking or profile."""
        if self.priority_ranking:
            return self.priority_ranking.to_weights()

        # Default weights based on decision profile
        profile_weights = {
            DecisionProfile.MVP_FAST: {
                "time_to_market": 0.4, "cost": 0.2, "scale": 0.1,
                "reliability": 0.15, "security": 0.15
            },
            DecisionProfile.COST_FIRST: {
                "time_to_market": 0.15, "cost": 0.4, "scale": 0.15,
                "reliability": 0.15, "security": 0.15
            },
            DecisionProfile.SCALE_FIRST: {
                "time_to_market": 0.1, "cost": 0.15, "scale": 0.4,
                "reliability": 0.2, "security": 0.15
            },
            DecisionProfile.SECURITY_FIRST: {
                "time_to_market": 0.1, "cost": 0.15, "scale": 0.15,
                "reliability": 0.2, "security": 0.4
            },
        }

        if self.decision_profile:
            return profile_weights[self.decision_profile]

        # Balanced default
        return {
            "time_to_market": 0.2, "cost": 0.2, "scale": 0.2,
            "reliability": 0.2, "security": 0.2
        }


# ============================================================
# LLM RESPONSE MODELS (for structured output)
# ============================================================

class IntakeResponse(BaseModel):
    """LLM response structure for intake node."""
    project_name: str
    summary: str
    requirements: List[Requirement]
    constraints: List[Constraint]
    questions: List[str]
    confidence: float = Field(ge=0, le=1)


class ProfileDetection(BaseModel):
    """LLM response for automatic profile detection."""
    profile: Optional[DecisionProfile]
    confidence: float = Field(ge=0, le=1)
    reasoning: str


class ConflictAnalysis(BaseModel):
    """LLM response for conflict detection."""
    conflicts: List[Conflict]
    overall_coherence: float = Field(ge=0, le=1)


class PatternSelection(BaseModel):
    """LLM response for pattern selection."""
    recommended_pattern: str
    justifications: Dict[str, str]  # pattern -> justification
    recommendation: str


class ParsedAnswer(BaseModel):
    """תשובה מפורסרת מהמשתמש."""
    id: str
    value: str
    normalized_key: str
    normalized_value: Any


class ParsedAnswers(BaseModel):
    """רשימת תשובות מפורסרות."""
    answers: List[ParsedAnswer] = Field(default_factory=list)


class CriticQuestion(BaseModel):
    """שאלה שהמבקר מבקש לשאול את המשתמש."""
    question: str
    impact: Literal["high", "medium", "low"] = "medium"
    why_it_matters: str


class SwapTarget(BaseModel):
    """יעד החלפת Pattern."""
    pattern: Optional[str] = None
    why: Optional[str] = None


class FailureMode(BaseModel):
    """מצב כשל פוטנציאלי."""
    failure: str
    severity: Literal["low", "medium", "high"] = "medium"
    mitigation: str


class MustFix(BaseModel):
    """בעיה שחייבים לתקן."""
    issue: str
    why: str
    suggested_change: str


class CriticAnalysis(BaseModel):
    """
    LLM response for critic node.

    מחזיר verdict ברור במקום "revise_pattern":
    - accept: לאשר את ה-Blueprint
    - accept_with_notes: לאשר עם הערות/אזהרות
    - ask_user: חסר מידע, חובה לשאול
    - swap_option: טעות בבחירה, להחליף לחלופה קיימת
    """
    confidence_score: float = Field(ge=0, le=1)
    strengths: List[str] = Field(default_factory=list)
    weaknesses: List[str] = Field(default_factory=list)

    # verdict ברור - זה מה שמנתב את הגרף
    verdict: Literal["accept", "accept_with_notes", "ask_user", "swap_option"] = "accept"

    # סיבת confidence נמוך
    low_confidence_reason: Optional[Literal[
        "missing_info",           # חסר מידע - צריך לשאול משתמש
        "over_engineering",       # פתרונות מורכבים מדי בלי הצדקה
        "conflicting_constraints", # אילוצים סותרים
        "weak_justification",      # הצדקה חלשה
        "wrong_choice",           # בחירה לא נכונה
        "other"                   # סיבה אחרת
    ]] = None

    # בעיות שחייבים לתקן
    must_fix: List[MustFix] = Field(default_factory=list)

    # שאלות לשאול את המשתמש (רק אם verdict=ask_user)
    questions_to_ask: List[CriticQuestion] = Field(default_factory=list)

    # יעד החלפה (רק אם verdict=swap_option)
    swap_to: Optional[SwapTarget] = None

    # מצבי כשל פוטנציאליים
    top_failure_modes: List[FailureMode] = Field(default_factory=list)

    # שדות ישנים לתאימות אחורה
    missing_info: Optional[str] = None
    conflicts: List[str] = Field(default_factory=list)

    # המלצה ישנה - נשמר לתאימות אחורה, אבל verdict הוא העיקרי
    recommendation: Literal["approve", "revise_pattern", "need_info", "resolve_conflicts"] = "approve"
