"""
MultiAgentCoordinator - Coordinates all agents in the system.

This coordinator uses browser-use Agent for actual browser interaction
while our agents provide enhanced perception, reflection, and planning.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional
from pathlib import Path

from browser_use import BrowserSession, BrowserProfile, Agent
from browser_use.agent.prompts import AgentMessagePrompt
from browser_use.browser.views import BrowserStateSummary
from browser_use.agent.views import AgentOutput

from .agent_message import EventBus, MessageType
from .shared_memory import SharedMemory, MemoryKey, ContextHints
from .browser_adapter import BrowserAdapter, create_browser_session, BrowserState
from .sequential_thinking import SequentialThinkingEngine, ThinkingContext

logger = logging.getLogger(__name__)


# =============================================================================
# ПАТЧ ДЛЯ УВЕЛИЧЕНИЯ ЛИМИТА ИНФОРМАЦИИ О СТРАНИЦЕ
# =============================================================================

_original_agent_message_prompt_init = AgentMessagePrompt.__init__

def _patched_agent_message_prompt_init(self, *args, **kwargs):
    """Патченый __init__ с увеличенным лимитом информации о страницы."""
    if 'max_clickable_elements_length' not in kwargs:
        kwargs['max_clickable_elements_length'] = 150000  # 150K вместо 40K
    _original_agent_message_prompt_init(self, *args, **kwargs)

AgentMessagePrompt.__init__ = _patched_agent_message_prompt_init


# =============================================================================
# ПАТЧ ДЛЯ ИНЪЕКЦИИ CONTEXT HINTS В ПРОМПТ
# =============================================================================

# Глобальная переменная для хранения текущих контекстных подсказок
_current_context_hints: Optional[ContextHints] = None

# Сохраняем оригинальный метод
_original_get_user_message = AgentMessagePrompt.get_user_message

def _patched_get_user_message(self, *args, **kwargs):
    """
    Патченый get_user_message который инъектирует ContextHints в промпт.

    Это ключевое изменение - теперь browser-use Agent ПОЛУЧАЕТ контекст от агентов!
    """
    # Получаем оригинальное сообщение
    original = _original_get_user_message(self, *args, **kwargs)

    # Если нет контекстных подсказок, возвращаем оригинал
    global _current_context_hints
    if _current_context_hints is None:
        return original

    # Форматируем контекст МИНИМАЛИСТИЧНО
    context_str = _current_context_hints.to_prompt_context()
    if not context_str:
        return original

    # Инъектируем контекст в UserMessage объект
    # UserMessage может иметь content как строку или список
    if hasattr(original, 'content'):
        if isinstance(original.content, str):
            # Добавляем контекст к строковому контенту
            original.content = f"{original.content}\n\n{context_str}"
        elif isinstance(original.content, list):
            # Добавляем контекст к списку контента (в первый текстовый элемент)
            for item in original.content:
                if hasattr(item, 'text'):
                    item.text = f"{item.text}\n\n{context_str}"
                    break

    return original

# Применяем патч
AgentMessagePrompt.get_user_message = _patched_get_user_message


# =============================================================================
# МИНИМАЛИСТИЧНЫЙ СИСТЕМНЫЙ ПРОМПТ
# =============================================================================

SYSTEM_PROMPT = """
Ты — автономный AI-агент для работы с браузером.

ПРАВИЛА:
- Выполняй задачу пользователя autonomously
- Останавливайся когда задача выполнена
- Не совершай финальную оплату без подтверждения
- Работай в одной вкладке
- Отвечай на русском языке
"""


class MultiAgentCoordinator:
    """
    Main coordinator for the multi-agent system.

    Uses browser-use Agent for execution while our agents
    provide enhanced capabilities through callbacks.
    """

    def __init__(
        self,
        browser_session: BrowserSession,
        llm: Any,
        max_steps: int = 25,
        debug: bool = False,
    ):
        self.browser_session = browser_session
        self.llm = llm
        self.max_steps = max_steps
        self.debug = debug
        self._logger = logging.getLogger("MultiAgentCoordinator")

        if debug:
            self._logger.setLevel(logging.DEBUG)
            logging.basicConfig(level=logging.DEBUG)

        # Initialize core components
        self.event_bus = EventBus()
        self.shared_memory = SharedMemory()
        self.browser_adapter = BrowserAdapter(browser_session, debug=debug)
        self.thinking_engine = SequentialThinkingEngine(
            self.shared_memory,
            max_steps=max_steps,
            debug=debug,
        )

        # Track execution state
        self._current_step = 0
        self._thinking_context: Optional[ThinkingContext] = None
        self._final_result: Optional[str] = None

        # Import agents for callback processing
        from agents.perception_agent import PerceptionAgent
        from agents.reflection_agent import ReflectionAgent

        self.perception_agent = PerceptionAgent(
            self.event_bus,
            self.shared_memory,
            llm,
            debug=debug,
        )
        self.reflection_agent = ReflectionAgent(
            self.event_bus,
            self.shared_memory,
            llm,
            debug=debug,
        )

    async def run_with_agents(self, task: str) -> str:
        """
        Run a task using browser-use Agent with our enhanced agents.

        Args:
            task: The task to execute

        Returns:
            Final result message
        """
        print("\n🤖 Запуск Multi-Agent System")

        # Initialize task
        await self.shared_memory.set(MemoryKey.TASK_DESCRIPTION, task)
        await self.shared_memory.set(MemoryKey.TASK_STATUS, "running")
        await self.shared_memory.set(MemoryKey.PROGRESS_SCORE, 0.0)

        # Create thinking context
        self._thinking_context = await self.thinking_engine.create_thinking_context(task)

        try:
            # Create browser-use agent with our callback
            agent = Agent(
                task=task,
                llm=self.llm,
                browser_session=self.browser_session,
                extend_system_message=SYSTEM_PROMPT,
                max_steps=self.max_steps,
                include_attributes=[
                    'aria-label', 'title', 'placeholder', 'name', 'type',
                    'value', 'href', 'id', 'class', 'role', 'aria-modal',
                    'aria-selected', 'aria-checked', 'checked', 'selected',
                    'disabled', 'readonly', 'text-content', 'alt', 'label',
                ],
                register_new_step_callback=self._step_callback,
            )

            # Run the agent
            history = await agent.run()

            # Process final result using final_result() method
            if history:
                result = history.final_result()
                # final_result() возвращает str или None
                if result and isinstance(result, str):
                    self._final_result = result
                else:
                    self._final_result = 'Задача выполнена'

            await self.shared_memory.set(MemoryKey.TASK_STATUS, "completed")

            return self._final_result or 'Задача выполнена'

        except Exception as e:
            self._logger.error(f"Error in run_with_agents: {e}")
            await self.shared_memory.set(MemoryKey.TASK_STATUS, "failed")
            raise

    async def _step_callback(
        self,
        browser_state: BrowserStateSummary,
        agent_output: AgentOutput,
        step: int,
    ) -> None:
        """
        Callback called by browser-use Agent after each step.

        This is where our agents process the state and provide insights.
        """
        self._current_step = step
        self._logger.info(f"\n{'='*50}")
        self._logger.info(f"STEP {step}/{self.max_steps}")
        self._logger.info(f"{'='*50}")

        try:
            # Update browser adapter with current state
            await self.browser_adapter.update_from_callback(browser_state, agent_output, step)

            # Get URL from browser session
            url = ""
            try:
                url = await self.browser_session.get_current_page_url() or ""
            except Exception:
                pass  # URL might not be available yet

            await self.shared_memory.set(MemoryKey.CURRENT_URL, url)

            # Create simplified browser state dict for our agents
            browser_state_dict = {
                "url": url,
                "title": "",  # Will be filled if available
                "clickable_elements": [],  # Will be extracted if available
                "is_modal_present": False,
                "pagination_detected": False,
            }

            # 1. Perception: Analyze current state
            if self.debug:
                self._logger.info("[1/2] Perception: Analyzing page...")

            perception_result = await self.perception_agent.process({
                "browser_state": browser_state_dict,
            })

            if perception_result.get("success"):
                perception_data = perception_result.get("perception", {})
                self._log_perception(perception_data)

                # 2. Reflection: Evaluate progress
                if self.debug:
                    self._logger.info("[2/2] Reflection: Evaluating...")

                last_result = self.shared_memory.get(MemoryKey.LAST_ACTION_RESULT)

                reflection_result = await self.reflection_agent.process({
                    "action_result": last_result,
                    "perception": perception_data,
                })

                if reflection_result.get("success"):
                    reflection_data = reflection_result.get("reflection", {})
                    self._log_reflection(reflection_data)

                    # Store action result for next step
                    action_result_dict = {
                        "success": True,
                        "action": str(agent_output.action) if hasattr(agent_output, 'action') else "unknown",
                    }
                    await self.shared_memory.set(MemoryKey.LAST_ACTION_RESULT, action_result_dict)

                # 3. Update global context hints for prompt injection
                # Это КЛЮЧЕВОЕ изменение - теперь browser-use Agent ПОЛУЧИТ контекст!
                global _current_context_hints
                hints_dict = self.shared_memory.get(MemoryKey.CONTEXT_HINTS)
                if hints_dict:
                    _current_context_hints = ContextHints.from_dict(hints_dict)
                    if self.debug:
                        self._logger.info(f"  [Context Injection] {len(_current_context_hints.observations)} observations, "
                                        f"{len(_current_context_hints.patterns)} patterns, "
                                        f"{len(_current_context_hints.warnings)} warnings")
                else:
                    _current_context_hints = None

        except Exception as e:
            self._logger.error(f"Error in step callback: {e}")

    def _log_perception(self, perception: Dict[str, Any]) -> None:
        """Log perception summary."""
        if not self.debug:
            return

        page_type = perception.get("page_type", "unknown")
        patterns = perception.get("patterns", [])
        modal = perception.get("modal_detected", False)

        self._logger.info(f"  [Perception] Page type: {page_type}")
        self._logger.info(f"  [Perception] Patterns: {', '.join(patterns) if patterns else 'none'}")
        self._logger.info(f"  [Perception] Modal: {'yes' if modal else 'no'}")

    def _log_reflection(self, reflection: Dict[str, Any]) -> None:
        """Log reflection summary."""
        if not self.debug:
            return

        success = reflection.get("action_successful", True)
        progress = reflection.get("progress_score", 0.0)
        next_action = reflection.get("next_action")

        self._logger.info(f"  [Reflection] Last action: {'success' if success else 'failed'}")
        self._logger.info(f"  [Reflection] Progress: {progress*100:.0f}%")
        if next_action:
            self._logger.info(f"  [Reflection] Next: {next_action}")

    def get_stats(self) -> Dict[str, Any]:
        """Get execution statistics."""
        return {
            "steps": self._current_step,
            "max_steps": self.max_steps,
            "progress": self.shared_memory.get(MemoryKey.PROGRESS_SCORE, 0.0),
            "task_status": self.shared_memory.get(MemoryKey.TASK_STATUS, "unknown"),
        }


async def create_coordinator(
    llm: Any,
    headless: bool = False,
    max_steps: int = 25,
    debug: bool = False,
) -> MultiAgentCoordinator:
    """
    Create a new coordinator with browser session.

    Args:
        llm: The LLM instance to use
        headless: Whether to run browser in headless mode
        max_steps: Maximum number of steps to execute
        debug: Enable debug logging

    Returns:
        MultiAgentCoordinator instance
    """
    browser_session = await create_browser_session(
        headless=headless,
        keep_alive=True,
    )

    return MultiAgentCoordinator(
        browser_session=browser_session,
        llm=llm,
        max_steps=max_steps,
        debug=debug,
    )
