"""
Agents package - Multi-agent system for Browser Agent.

Contains specialized agents:
- PerceptionAgent: Analyzes page state and detects patterns
- ReflectionAgent: Evaluates progress and decides next steps
"""

from .perception_agent import PerceptionAgent
from .reflection_agent import ReflectionAgent

__all__ = [
    "PerceptionAgent",
    "ReflectionAgent",
]
