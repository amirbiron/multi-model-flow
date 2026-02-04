"""
Architect Agent - Agent Package
================================
Core agent components including state, graph, and nodes.

Note: Use explicit imports to avoid circular dependencies:
    from src.agent.state import ProjectContext
    from src.agent.graph import run_agent
"""

__all__ = [
    "ProjectContext",
    "Blueprint",
    "ArchitecturalDecision",
    "create_architect_graph",
    "run_agent",
    "continue_conversation",
]


def __getattr__(name):
    """Lazy imports to avoid circular dependencies."""
    if name in ("ProjectContext", "Blueprint", "ArchitecturalDecision"):
        from .state import ProjectContext, Blueprint, ArchitecturalDecision
        return locals()[name]
    elif name in ("create_architect_graph", "run_agent", "continue_conversation"):
        from .graph import create_architect_graph, run_agent, continue_conversation
        return locals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
