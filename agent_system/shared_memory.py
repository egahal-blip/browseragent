"""
Shared Memory - Thread-safe shared memory for agents.

Agents can share context, observations, and results through shared memory.
"""

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set
import logging

logger = logging.getLogger(__name__)


class MemoryKey(Enum):
    """Keys for shared memory."""

    # Task context
    TASK_DESCRIPTION = "task_description"
    TASK_GOAL = "task_goal"
    TASK_STATUS = "task_status"

    # Browser state
    CURRENT_URL = "current_url"
    PAGE_TITLE = "page_title"
    DOM_CONTENT = "dom_content"

    # Perception data
    PERCEPTION_RESULT = "perception_result"
    DETECTED_PATTERNS = "detected_patterns"
    INTERACTIVE_ELEMENTS = "interactive_elements"

    # Reflection data
    REFLECTION_RESULT = "reflection_result"
    PROGRESS_SCORE = "progress_score"
    ACTION_HISTORY = "action_history"
    ERROR_HISTORY = "error_history"

    # Action data
    LAST_ACTION = "last_action"
    LAST_ACTION_RESULT = "last_action_result"
    PENDING_ACTIONS = "pending_actions"

    # Planning
    CURRENT_PLAN = "current_plan"
    NEXT_STEP = "next_step"
    THOUGHT_CHAIN = "thought_chain"

    # User state
    USER_LOGGED_IN = "user_logged_in"
    CART_ITEMS = "cart_items"
    CHECKOUT_STAGE = "checkout_stage"

    # Context hints (для инъекции в промпт browser-use Agent)
    CONTEXT_HINTS = "context_hints"


@dataclass
class PerceptionData:
    """Data from perception agent."""

    page_type: Optional[str] = None  # e.g., "catalog", "product", "cart", "checkout"
    patterns: List[str] = field(default_factory=list)
    interactive_elements: List[Dict[str, Any]] = field(default_factory=list)
    modal_detected: bool = False
    pagination_detected: bool = False
    forms_detected: List[Dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.0
    observations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "page_type": self.page_type,
            "patterns": self.patterns,
            "interactive_elements": self.interactive_elements,
            "modal_detected": self.modal_detected,
            "pagination_detected": self.pagination_detected,
            "forms_detected": self.forms_detected,
            "confidence": self.confidence,
            "observations": self.observations,
        }


@dataclass
class ReflectionData:
    """Data from reflection agent."""

    action_successful: bool
    progress_made: bool
    confidence: float
    next_action: Optional[str] = None
    reasoning: Optional[str] = None
    errors: List[str] = field(default_factory=list)
    suggested_corrections: List[str] = field(default_factory=list)
    should_continue: bool = True
    should_correct: bool = False
    progress_score: float = 0.0  # 0.0 to 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_successful": self.action_successful,
            "progress_made": self.progress_made,
            "confidence": self.confidence,
            "next_action": self.next_action,
            "reasoning": self.reasoning,
            "errors": self.errors,
            "suggested_corrections": self.suggested_corrections,
            "should_continue": self.should_continue,
            "should_correct": self.should_correct,
            "progress_score": self.progress_score,
        }


@dataclass
class ActionData:
    """Data about an action."""

    action_type: str
    target_element: Optional[str] = None
    value: Optional[str] = None
    timestamp: float = field(default_factory=lambda: __import__("time").time())
    result: Optional[str] = None
    error: Optional[str] = None
    screenshot_before: Optional[str] = None
    screenshot_after: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_type": self.action_type,
            "target_element": self.target_element,
            "value": self.value,
            "timestamp": self.timestamp,
            "result": self.result,
            "error": self.error,
        }


@dataclass
class ThoughtStep:
    """A single step in the thought chain."""

    step_number: int
    thought: str  # What the agent thinks
    observation: str  # What the agent observes
    action: str  # What the agent plans to do
    reflection: Optional[str] = None  # Evaluation of previous action
    next_thought: Optional[str] = None  # What comes next
    confidence: float = 0.5
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_number": self.step_number,
            "thought": self.thought,
            "observation": self.observation,
            "action": self.action,
            "reflection": self.reflection,
            "next_thought": self.next_thought,
            "confidence": self.confidence,
            "metadata": self.metadata,
        }


@dataclass
class ContextHints:
    """
    Контекстные подсказки от агентов (БЕЗ жёстких инструкций!).

    Используется для инъекции в промпт browser-use Agent.
    """

    observations: List[str] = field(default_factory=list)
    patterns: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    suggested_categories: List[str] = field(default_factory=list)

    def to_prompt_context(self) -> str:
        """
        МИНИМАЛИСТИЧНОЕ форматирование для промпта.

        Возвращает только самую важную информацию без жёстких инструкций.
        """
        parts = []

        if self.observations:
            obs = self.observations[:3]  # Максимум 3 наблюдения
            parts.append("### Наблюдение:\n" + "\n".join(f"- {o}" for o in obs))

        if self.patterns:
            patterns_str = ", ".join(self.patterns[:5])  # Максимум 5 паттернов
            parts.append(f"### Паттерны: {patterns_str}")

        if self.warnings:
            warnings_list = self.warnings[:2]  # Максимум 2 предупреждения
            parts.append("### Важно:\n" + "\n".join(f"- {w}" for w in warnings_list))

        if self.suggested_categories:
            cats = ", ".join(self.suggested_categories[:4])
            parts.append(f"### Категории элементов: {cats}")

        return "\n\n".join(parts)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "observations": self.observations,
            "patterns": self.patterns,
            "warnings": self.warnings,
            "suggested_categories": self.suggested_categories,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ContextHints":
        return cls(
            observations=data.get("observations", []),
            patterns=data.get("patterns", []),
            warnings=data.get("warnings", []),
            suggested_categories=data.get("suggested_categories", []),
        )


class SharedMemory:
    """
    Thread-safe shared memory for agent communication.

    Uses asyncio locks for concurrent access safety.
    """

    def __init__(self):
        self._data: Dict[MemoryKey, Any] = {}
        self._locks: Dict[MemoryKey, asyncio.Lock] = {}
        self._main_lock = asyncio.Lock()
        self._subscribers: Dict[MemoryKey, Set[str]] = {}

    def get(self, key: MemoryKey, default: Any = None) -> Any:
        """Get value from memory."""
        return self._data.get(key, default)

    async def set(self, key: MemoryKey, value: Any) -> None:
        """Set value in memory with lock."""
        lock = self._get_lock(key)
        async with lock:
            old_value = self._data.get(key)
            self._data[key] = value

            # Notify subscribers if value changed
            if old_value != value:
                await self._notify_subscribers(key, value)

    async def update(self, key: MemoryKey, updates: Dict[str, Any]) -> None:
        """Update nested dictionary values."""
        lock = self._get_lock(key)
        async with lock:
            current = self._data.get(key, {})
            if isinstance(current, dict):
                current.update(updates)
            else:
                self._data[key] = updates

            await self._notify_subscribers(key, self._data[key])

    def delete(self, key: MemoryKey) -> None:
        """Delete key from memory."""
        self._data.pop(key, None)
        self._locks.pop(key, None)

    async def wait_for(
        self, key: MemoryKey, timeout: float = 5.0, predicate=None
    ) -> Any:
        """
        Wait for a value to be set or match a predicate.

        Args:
            key: The memory key to wait for
            timeout: Maximum time to wait
            predicate: Optional function that must return True for the value

        Returns:
            The value that satisfied the condition
        """
        start_time = __import__("time").time()

        while __import__("time").time() - start_time < timeout:
            value = self.get(key)
            if value is not None:
                if predicate is None or predicate(value):
                    return value
            await asyncio.sleep(0.1)

        raise asyncio.TimeoutError(f"Timeout waiting for {key}")

    def subscribe(self, key: MemoryKey, agent_name: str) -> None:
        """Subscribe an agent to changes in a key."""
        if key not in self._subscribers:
            self._subscribers[key] = set()
        self._subscribers[key].add(agent_name)

    def unsubscribe(self, key: MemoryKey, agent_name: str) -> None:
        """Unsubscribe an agent from a key."""
        if key in self._subscribers:
            self._subscribers[key].discard(agent_name)

    def get_snapshot(self) -> Dict[MemoryKey, Any]:
        """Get a snapshot of all current values."""
        return self._data.copy()

    def clear(self) -> None:
        """Clear all data."""
        self._data.clear()
        self._locks.clear()

    def _get_lock(self, key: MemoryKey) -> asyncio.Lock:
        """Get or create lock for a key."""
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]

    async def _notify_subscribers(self, key: MemoryKey, value: Any) -> None:
        """Notify subscribers of a value change."""
        subscribers = self._subscribers.get(key, set())
        if subscribers:
            logger.debug(f"Notifying {len(subscribers)} subscribers for {key}")

    def get_context_summary(self) -> Dict[str, Any]:
        """Get a summary of current context."""
        return {
            "url": self.get(MemoryKey.CURRENT_URL),
            "page_title": self.get(MemoryKey.PAGE_TITLE),
            "page_type": self.get(MemoryKey.PERCEPTION_RESULT, {}).get("page_type"),
            "progress": self.get(MemoryKey.PROGRESS_SCORE, 0.0),
            "last_action": self.get(MemoryKey.LAST_ACTION),
            "task_status": self.get(MemoryKey.TASK_STATUS, "pending"),
        }
