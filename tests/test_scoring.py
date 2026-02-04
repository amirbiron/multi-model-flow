"""
Architect Agent - Tests for Nodes
==================================
Unit tests for the agent nodes.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.agent.state import (
    ProjectContext, Requirement, Constraint, Priority,
    DecisionProfile, PriorityRanking
)
from src.knowledge.decision_matrix import (
    score_pattern, score_all_patterns, get_top_recommendations,
    detect_conflicts
)


# ============================================================
# FIXTURES
# ============================================================

@pytest.fixture
def sample_context():
    """Create a sample ProjectContext for testing."""
    ctx = ProjectContext(
        session_id="test-session-123",
        initial_summary="אני רוצה לבנות מערכת e-commerce עם 100K משתמשים"
    )
    ctx.project_name = "E-Commerce Platform"
    ctx.requirements = [
        Requirement(
            category="functional",
            description="מערכת הזמנות עם עגלת קניות",
            priority=Priority.HIGH
        ),
        Requirement(
            category="non_functional",
            description="תמיכה ב-100,000 משתמשים במקביל",
            priority=Priority.CRITICAL
        )
    ]
    ctx.constraints = [
        Constraint(
            type="budget",
            description="תקציב של $2000 לחודש",
            severity=Priority.HIGH
        ),
        Constraint(
            type="timeline",
            description="צריך לצאת לאוויר תוך 3 חודשים",
            severity=Priority.MEDIUM
        )
    ]
    return ctx


@pytest.fixture
def sample_priorities():
    """Create sample priority ranking."""
    return PriorityRanking(
        time_to_market=5,
        cost=4,
        scale=3,
        reliability=3,
        security=2
    )


# ============================================================
# SCORING TESTS
# ============================================================

class TestScoringSystem:
    """Tests for the deterministic scoring system."""

    def test_score_pattern_basic(self, sample_priorities):
        """Test basic pattern scoring."""
        scored = score_pattern(
            pattern_name="monolith",
            priorities=sample_priorities,
            constraints=[]
        )

        assert scored.name == "monolith"
        assert 0 <= scored.score <= 100
        assert scored.viable is True
        assert len(scored.breakdown) == 5

    def test_score_pattern_with_constraints(self, sample_priorities, sample_context):
        """Test scoring with constraints applied."""
        scored_without = score_pattern(
            pattern_name="microservices",
            priorities=sample_priorities,
            constraints=[]
        )

        scored_with = score_pattern(
            pattern_name="microservices",
            priorities=sample_priorities,
            constraints=sample_context.constraints
        )

        # Constraints should reduce score
        assert scored_with.score < scored_without.score

    def test_score_all_patterns(self, sample_priorities):
        """Test scoring all patterns."""
        all_scored = score_all_patterns(
            priorities=sample_priorities,
            constraints=[]
        )

        assert len(all_scored) >= 4
        # Should be sorted by score
        scores = [p.score for p in all_scored]
        assert scores == sorted(scores, reverse=True)

    def test_get_top_recommendations(self, sample_priorities):
        """Test getting top N recommendations."""
        top_3 = get_top_recommendations(
            priorities=sample_priorities,
            constraints=[],
            top_n=3
        )

        assert len(top_3) == 3
        assert all(p.viable for p in top_3)

    def test_mvp_fast_profile_favors_monolith(self):
        """Test that MVP_FAST profile scores monolith highly."""
        all_scored = score_all_patterns(
            priorities=None,
            constraints=[],
            profile=DecisionProfile.MVP_FAST
        )

        # Monolith should be in top 2 for MVP_FAST
        top_names = [p.name for p in all_scored[:2]]
        assert "monolith" in top_names or "modular_monolith" in top_names

    def test_scale_first_profile_favors_microservices(self):
        """Test that SCALE_FIRST profile scores microservices highly."""
        all_scored = score_all_patterns(
            priorities=None,
            constraints=[],
            profile=DecisionProfile.SCALE_FIRST
        )

        # Microservices or event_driven should be in top 2
        top_names = [p.name for p in all_scored[:2]]
        scalable_patterns = ["microservices", "event_driven", "serverless"]
        assert any(name in scalable_patterns for name in top_names)


# ============================================================
# CONFLICT DETECTION TESTS
# ============================================================

class TestConflictDetection:
    """Tests for conflict detection rules."""

    def test_detect_scale_vs_cost_conflict(self):
        """Test detection of scale vs cost conflict."""
        requirements = [
            Requirement(
                category="non_functional",
                description="Support for 1 million concurrent users with high scale",
                priority=Priority.HIGH
            )
        ]
        constraints = [
            Constraint(
                type="budget",
                description="Limited budget",
                severity=Priority.CRITICAL
            )
        ]

        conflicts = detect_conflicts(requirements, constraints)

        assert len(conflicts) >= 1
        assert any("scale" in c["name"].lower() or "cost" in c["name"].lower()
                   for c in conflicts)

    def test_no_conflicts_for_simple_project(self):
        """Test that simple projects don't have false conflicts."""
        requirements = [
            Requirement(
                category="functional",
                description="דף נחיתה פשוט",
                priority=Priority.MEDIUM
            )
        ]
        constraints = []

        conflicts = detect_conflicts(requirements, constraints)

        # Simple project should have no conflicts
        assert len(conflicts) == 0


# ============================================================
# STATE TESTS
# ============================================================

class TestProjectContext:
    """Tests for ProjectContext state model."""

    def test_add_message(self, sample_context):
        """Test adding messages to history."""
        initial_count = len(sample_context.conversation_history)

        sample_context.add_message("user", "שאלה חדשה")
        sample_context.add_message("assistant", "תשובה")

        assert len(sample_context.conversation_history) == initial_count + 2
        assert sample_context.conversation_history[-1]["role"] == "assistant"

    def test_is_done_false_without_blueprint(self, sample_context):
        """Test is_done returns False without blueprint."""
        assert sample_context.is_done() is False

    def test_get_priority_weights(self, sample_context, sample_priorities):
        """Test getting priority weights."""
        sample_context.priority_ranking = sample_priorities
        weights = sample_context.get_priority_weights()

        assert sum(weights.values()) == pytest.approx(1.0, rel=0.01)
        assert weights["time_to_market"] > weights["security"]

    def test_has_unresolved_conflicts(self, sample_context):
        """Test checking for unresolved conflicts."""
        from src.agent.state import Conflict

        sample_context.conflicts = [
            Conflict(
                requirements=["req1", "req2"],
                explanation="Test conflict",
                compromises=["option1", "option2"],
                resolved=False
            )
        ]

        assert sample_context.has_unresolved_conflicts() is True

        sample_context.conflicts[0].resolved = True
        assert sample_context.has_unresolved_conflicts() is False


# ============================================================
# RUN TESTS
# ============================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
