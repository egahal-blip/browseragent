"""
Agent Message - Message types and EventBus for agent communication.

Agents communicate through async message passing using the event bus pattern.
"""

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
import logging

logger = logging.getLogger(__name__)


class MessageType(Enum):
    """Types of messages that can be sent between agents."""

    # Perception messages
    PERCEPTION_PAGE_ANALYZED = "perception_page_analyzed"
    PERCEPTION_PATTERN_DETECTED = "perception_pattern_detected"
    PERCEPTION_ELEMENTS_FOUND = "perception_elements_found"

    # Reflection messages
    REFLECTION_ACTION_EVALUATED = "reflection_action_evaluated"
    REFLECTION_PROGRESS_UPDATED = "reflection_progress_updated"
    REFLECTION_ERROR_ANALYZED = "reflection_error_analyzed"
    REFLECTION_DECISION_MADE = "reflection_decision_made"

    # Action messages
    ACTION_STARTED = "action_started"
    ACTION_COMPLETED = "action_completed"
    ACTION_FAILED = "action_failed"

    # Planning messages
    PLANNING_STEP_CREATED = "planning_step_created"
    PLANNING_NEXT_ACTION = "planning_next_action"
    PLANNING_CORRECTION = "planning_correction"

    # System messages
    SYSTEM_SHUTDOWN = "system_shutdown"
    SYSTEM_ERROR = "system_error"


@dataclass
class AgentMessage:
    """A message sent between agents."""

    sender: str
    message_type: MessageType
    content: Any
    recipient: Optional[str] = None
    timestamp: float = field(default_factory=lambda: __import__("time").time())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        recipient_str = self.recipient or "broadcast"
        return f"[{self.sender} -> {recipient_str}] {self.message_type.value}"


MessageHandler = Callable[[AgentMessage], Any]


class EventBus:
    """
    Async event bus for agent communication.

    Agents can publish messages and subscribe to specific message types.
    """

    def __init__(self):
        self._subscribers: Dict[MessageType, List[MessageHandler]] = {}
        self._agent_subscribers: Dict[str, List[MessageType]] = {}
        self._message_history: List[AgentMessage] = []
        self._max_history = 1000
        self._lock = asyncio.Lock()

    async def publish(self, message: AgentMessage) -> None:
        """Publish a message to all subscribers."""
        async with self._lock:
            # Add to history
            self._message_history.append(message)
            if len(self._message_history) > self._max_history:
                self._message_history.pop(0)

        # Get subscribers for this message type
        subscribers = self._subscribers.get(message.message_type, [])

        if not subscribers:
            logger.debug(f"No subscribers for {message.message_type}")
            return

        # Deliver to all subscribers
        tasks = []
        for handler in subscribers:
            tasks.append(self._deliver_message(handler, message))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _deliver_message(
        self, handler: MessageHandler, message: AgentMessage
    ) -> None:
        """Deliver message to a handler with error handling."""
        try:
            result = handler(message)
            if asyncio.iscoroutine(result):
                await result
        except Exception as e:
            logger.error(f"Error delivering message to handler: {e}")

    def subscribe(
        self,
        message_type: MessageType,
        handler: MessageHandler,
        agent_name: Optional[str] = None,
    ) -> Callable[[], None]:
        """
        Subscribe to a message type.

        Returns a function that can be called to unsubscribe.
        """
        if message_type not in self._subscribers:
            self._subscribers[message_type] = []

        self._subscribers[message_type].append(handler)

        if agent_name:
            if agent_name not in self._agent_subscribers:
                self._agent_subscribers[agent_name] = []
            self._agent_subscribers[agent_name].append(message_type)

        # Return unsubscribe function
        def unsubscribe():
            if message_type in self._subscribers:
                self._subscribers[message_type].remove(handler)
            if agent_name and agent_name in self._agent_subscribers:
                if message_type in self._agent_subscribers[agent_name]:
                    self._agent_subscribers[agent_name].remove(message_type)

        return unsubscribe

    def get_message_history(
        self,
        sender: Optional[str] = None,
        message_type: Optional[MessageType] = None,
        limit: int = 100,
    ) -> List[AgentMessage]:
        """Get message history with optional filtering."""
        history = self._message_history

        if sender:
            history = [m for m in history if m.sender == sender]
        if message_type:
            history = [m for m in history if m.message_type == message_type]

        return history[-limit:]

    def clear_history(self) -> None:
        """Clear message history."""
        self._message_history.clear()

    def get_agent_subscriptions(self, agent_name: str) -> List[MessageType]:
        """Get all message types an agent is subscribed to."""
        return self._agent_subscribers.get(agent_name, [])


class MessageBus:
    """
    High-level message bus with additional features.

    Provides request-response pattern and message filtering.
    """

    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
        self._pending_requests: Dict[str, asyncio.Future] = {}
        self._request_counter = 0

    async def publish(self, message: AgentMessage) -> None:
        """Publish a message."""
        await self.event_bus.publish(message)

    async def request(
        self, message: AgentMessage, timeout: float = 5.0
    ) -> Optional[AgentMessage]:
        """
        Send a request and wait for response.

        Returns the response message or None if timeout.
        """
        import uuid

        request_id = str(uuid.uuid4())
        message.metadata["request_id"] = request_id
        message.metadata["is_request"] = True

        # Create future for response
        future = asyncio.Future()
        self._pending_requests[request_id] = future

        # Subscribe to response
        response_type = MessageType(
            f"{message.message_type.value}_response"
        )

        def response_handler(resp: AgentMessage):
            if resp.metadata.get("request_id") == request_id:
                if not future.done():
                    future.set_result(resp)

        self.event_bus.subscribe(response_type, response_handler)

        # Send request
        await self.event_bus.publish(message)

        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning(f"Request {request_id} timed out")
            return None
        finally:
            self._pending_requests.pop(request_id, None)

    def subscribe(
        self, message_type: MessageType, handler: MessageHandler
    ) -> Callable[[], None]:
        """Subscribe to a message type."""
        return self.event_bus.subscribe(message_type, handler)
