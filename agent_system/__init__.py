"""
Agent System - Multi-agent architecture for Browser Agent.

This module provides the base infrastructure for the multi-agent system:
- AgentBase: Base class for all agents
- AgentMessage: Message types and EventBus
- SharedMemory: Thread-safe shared memory
- BrowserAdapter: Adapter for browser-use integration
- MultiAgentCoordinator: Main coordinator

КРИТИЧЕСКИЕ ТРЕБОВАНИЯ:
- NO хардкод селекторов
- NO жёстких инструкций
- Минималистичные системные промпты
"""

from .agent_base import AgentBase, AgentCapability
from .agent_message import (
    MessageType,
    AgentMessage,
    MessageBus,
    EventBus,
)
from .shared_memory import (
    SharedMemory,
    MemoryKey,
    PerceptionData,
    ReflectionData,
    ActionData,
)
from .browser_adapter import BrowserAdapter, BrowserState

__all__ = [
    # Base classes
    "AgentBase",
    "AgentCapability",
    # Messaging
    "MessageType",
    "AgentMessage",
    "MessageBus",
    "EventBus",
    # Memory
    "SharedMemory",
    "MemoryKey",
    "PerceptionData",
    "ReflectionData",
    "ActionData",
    # Browser
    "BrowserAdapter",
    "BrowserState",
]
