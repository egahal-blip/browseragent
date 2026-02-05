"""
Agent Base - Base class for all agents in the multi-agent system.

Each agent has specific capabilities and can communicate through the event bus.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
import logging

from .agent_message import EventBus, MessageType, AgentMessage
from .shared_memory import SharedMemory, MemoryKey

logger = logging.getLogger(__name__)


class AgentCapability(Enum):
    """Capabilities that agents can have."""

    # Perception capabilities
    PERCEPTION = "perception"
    PATTERN_DETECTION = "pattern_detection"
    DOM_ANALYSIS = "dom_analysis"

    # Reflection capabilities
    REFLECTION = "reflection"
    PROGRESS_EVALUATION = "progress_evaluation"
    ERROR_ANALYSIS = "error_analysis"
    DECISION_MAKING = "decision_making"

    # Action capabilities
    ACTION_EXECUTION = "action_execution"
    FORM_FILLING = "form_filling"
    NAVIGATION = "navigation"
    ELEMENT_INTERACTION = "element_interaction"

    # Planning capabilities
    PLANNING = "planning"
    SEQUENTIAL_THINKING = "sequential_thinking"


@dataclass
class AgentConfig:
    """Configuration for an agent."""

    name: str
    capabilities: Set[AgentCapability]
    system_prompt: str
    max_tokens: int = 4096
    temperature: float = 0.0
    debug: bool = False


class AgentBase(ABC):
    """
    Base class for all agents.

    Each agent must:
    1. Define its capabilities
    2. Implement process() method
    3. Use event bus for communication
    4. Access shared memory for context
    """

    def __init__(
        self,
        config: AgentConfig,
        event_bus: EventBus,
        shared_memory: SharedMemory,
    ):
        self.config = config
        self.event_bus = event_bus
        self.shared_memory = shared_memory
        self._logger = logging.getLogger(f"Agent.{config.name}")

        if config.debug:
            self._logger.setLevel(logging.DEBUG)

        # Subscribe to relevant messages based on capabilities
        self._subscribe_to_messages()

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def capabilities(self) -> Set[AgentCapability]:
        return self.config.capabilities

    @abstractmethod
    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process input data and return result.

        This is the main method that each agent must implement.
        It should be minimal and focused on the agent's specific task.
        """
        pass

    async def send_message(
        self,
        message_type: MessageType,
        content: Any,
        recipient: Optional[str] = None,
    ) -> None:
        """Send a message through the event bus."""
        message = AgentMessage(
            sender=self.name,
            recipient=recipient,
            message_type=message_type,
            content=content,
        )
        await self.event_bus.publish(message)

    async def receive_message(self, message: AgentMessage) -> None:
        """
        Handle incoming message.

        Override this method to handle specific message types.
        """
        self._logger.debug(f"Received message: {message.message_type} from {message.sender}")

    def _subscribe_to_messages(self) -> None:
        """Subscribe to relevant message types based on capabilities."""
        # This can be overridden by subclasses
        pass

    def get_memory(self, key: MemoryKey) -> Any:
        """Get data from shared memory (synchronous)."""
        return self.shared_memory.get(key)

    async def set_memory(self, key: MemoryKey, value: Any) -> None:
        """Set data in shared memory (asynchronous)."""
        await self.shared_memory.set(key, value)

    def log_debug(self, message: str) -> None:
        """Log debug message."""
        self._logger.debug(f"[{self.name}] {message}")

    def log_info(self, message: str) -> None:
        """Log info message."""
        self._logger.info(f"[{self.name}] {message}")

    def log_warning(self, message: str) -> None:
        """Log warning message."""
        self._logger.warning(f"[{self.name}] {message}")

    def log_error(self, message: str) -> None:
        """Log error message."""
        self._logger.error(f"[{self.name}] {message}")
