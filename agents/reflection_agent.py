"""
Reflection Agent - Evaluates progress and decides next steps.

КРИТИЧЕСКИ ВАЖНО:
- NO жёстких инструкций
- Минималистичный промпт
- Автономное принятие решений
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import logging

from agent_system.agent_base import AgentBase, AgentCapability, AgentConfig
from agent_system.agent_message import MessageType
from agent_system.shared_memory import (
    SharedMemory,
    MemoryKey,
    ReflectionData,
    ContextHints,
)

logger = logging.getLogger(__name__)


# Минималистичный системный промпт для Reflection Agent
REFLECTION_SYSTEM_PROMPT = """
Ты — агент рефлексии для браузера.

Твоя задача — оценивать прогресс и решать что делать дальше:
1. Было ли действие успешным?
2. Продвинулась ли задача вперёд?
3. Что делать дальше?
4. Нужно ли скорректировать план?

Отвечай на русском языке, работай autonomously.
"""


class ReflectionAgent(AgentBase):
    """
    Agent for reflecting on actions and deciding next steps.

    Evaluates progress, analyzes errors, and makes decisions autonomously.
    """

    def __init__(
        self,
        event_bus,
        shared_memory: SharedMemory,
        llm: Any,
        debug: bool = False,
    ):
        config = AgentConfig(
            name="ReflectionAgent",
            capabilities={
                AgentCapability.REFLECTION,
                AgentCapability.PROGRESS_EVALUATION,
                AgentCapability.ERROR_ANALYSIS,
                AgentCapability.DECISION_MAKING,
            },
            system_prompt=REFLECTION_SYSTEM_PROMPT,
            debug=debug,
        )

        super().__init__(config, event_bus, shared_memory)
        self.llm = llm

        # Track progress over time
        self._progress_history: List[float] = []
        self._action_history: List[Dict[str, Any]] = []

        # Subscribe to relevant messages
        self._subscribe_to_messages()

    def _subscribe_to_messages(self) -> None:
        """Subscribe to relevant message types."""
        self.event_bus.subscribe(
            MessageType.ACTION_COMPLETED, self._on_action_completed
        )
        self.event_bus.subscribe(
            MessageType.ACTION_FAILED, self._on_action_failed
        )
        self.event_bus.subscribe(
            MessageType.PERCEPTION_PAGE_ANALYZED, self._on_page_analyzed
        )

    async def _on_action_completed(self, message) -> None:
        """Handle action completion by reflecting on it."""
        action_result = message.content
        await self.reflect_on_action(action_result)

    async def _on_action_failed(self, message) -> None:
        """Handle action failure."""
        error_info = message.content
        await self.analyze_error(error_info)

    async def _on_page_analyzed(self, message) -> None:
        """Handle page analysis by updating context."""
        perception = message.content
        await self._update_progress_from_perception(perception)

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process input and produce reflection data.

        Args:
            input_data: Contains action_result, perception, or other context

        Returns:
            Dictionary with reflection results
        """
        action_result = input_data.get("action_result")
        perception = input_data.get("perception")

        try:
            # Perform reflection
            reflection = await self.reflect_on_action(action_result)

            # Store in shared memory
            await self.set_memory(MemoryKey.REFLECTION_RESULT, reflection.to_dict())
            await self.set_memory(MemoryKey.PROGRESS_SCORE, reflection.progress_score)

            # Update ContextHints with warnings from reflection
            await self._update_context_hints(reflection, perception)

            # Publish reflection result
            await self.send_message(
                MessageType.REFLECTION_ACTION_EVALUATED,
                reflection.to_dict(),
            )

            # Publish progress update
            await self.send_message(
                MessageType.REFLECTION_PROGRESS_UPDATED,
                {
                    "progress": reflection.progress_score,
                    "should_continue": reflection.should_continue,
                },
            )

            # Make decision about next action
            if reflection.next_action:
                await self.send_message(
                    MessageType.REFLECTION_DECISION_MADE,
                    {"next_action": reflection.next_action},
                )

            self.log_info(
                f"Reflection: success={reflection.action_successful}, "
                f"progress={reflection.progress_score:.2f}"
            )

            return {
                "success": True,
                "reflection": reflection.to_dict(),
            }

        except Exception as e:
            self.log_error(f"Error in process: {e}")
            return {"success": False, "error": str(e)}

    async def reflect_on_action(
        self, action_result: Optional[Any] = None
    ) -> ReflectionData:
        """
        Reflect on an action and evaluate progress.

        Args:
            action_result: Result of the previous action

        Returns:
            ReflectionData with evaluation and decisions
        """
        # Determine if action was successful
        action_successful = await self._evaluate_action_success(action_result)

        # Determine if progress was made
        progress_made = await self._evaluate_progress_made(action_result)

        # Calculate progress score
        progress_score = await self._calculate_progress_score(action_result)

        # Generate next action suggestion
        next_action = await self._decide_next_action(action_result, progress_score)

        # Generate reasoning
        reasoning = await self._generate_reasoning(action_result, progress_made)

        # Check for errors
        errors = await self._identify_errors(action_result)

        # Generate corrections if needed
        suggested_corrections = []
        if errors:
            suggested_corrections = await self._generate_corrections(errors)

        # Decide whether to continue
        should_continue = await self.should_continue(progress_score, errors)

        # Decide whether to correct
        should_correct = len(errors) > 0 and not action_successful

        return ReflectionData(
            action_successful=action_successful,
            progress_made=progress_made,
            confidence=await self._calculate_confidence(progress_score),
            next_action=next_action,
            reasoning=reasoning,
            errors=errors,
            suggested_corrections=suggested_corrections,
            should_continue=should_continue,
            should_correct=should_correct,
            progress_score=progress_score,
        )

    async def _evaluate_action_success(self, action_result: Optional[Any]) -> bool:
        """Evaluate if the action was successful."""
        if action_result is None:
            # No action result means we're at the start
            return True

        # Check if action_result has success attribute
        if hasattr(action_result, "success"):
            return action_result.success

        # Check if it's a dict with success key
        if isinstance(action_result, dict):
            return action_result.get("success", True)

        # Default to true if no clear failure indicator
        return True

    async def _evaluate_progress_made(self, action_result: Optional[Any]) -> bool:
        """Evaluate if progress was made toward the goal."""
        # Get previous and current progress
        previous_score = self._progress_history[-1] if self._progress_history else 0.0
        current_score = await self._calculate_progress_score(action_result)

        # Progress is made if score increased
        return current_score > previous_score

    async def _calculate_progress_score(self, action_result: Optional[Any]) -> float:
        """
        Calculate overall progress score (0.0 to 1.0).

        This estimates how close we are to completing the task.
        """
        # Get task goal
        task = self.shared_memory.get(MemoryKey.TASK_DESCRIPTION)
        if not task:
            return 0.0

        # Get current perception
        perception = self.shared_memory.get(MemoryKey.PERCEPTION_RESULT, {})
        page_type = perception.get("page_type", "unknown")

        # Base score on page type and task
        score = 0.0

        # Analyze task to understand goal
        task_lower = task.lower()

        # Shopping tasks
        if any(word in task_lower for word in ["купи", "закажи", "добавь", "buy", "order", "add"]):
            # Progress based on page type
            if page_type == "catalog":
                score = 0.2
            elif page_type == "product":
                score = 0.4
            elif page_type == "cart":
                score = 0.6
            elif page_type == "checkout":
                score = 0.8
            elif "completed" in page_type or "success" in page_type:
                score = 1.0

        # Search tasks
        elif any(word in task_lower for word in ["найди", "поиск", "search", "find"]):
            url = self.shared_memory.get(MemoryKey.CURRENT_URL, "")
            # If we're on a result page with content
            if perception.get("interactive_elements"):
                score = 0.5
            # If we found what we're looking for
            if action_result and hasattr(action_result, "success") and action_result.success:
                score = 0.8

        # Navigation tasks
        elif any(word in task_lower for word in ["зайди", "открой", "go to", "open", "visit"]):
            # Success if we navigated to the target
            score = 0.7 if page_type != "unknown" else 0.3

        # Track progress history
        self._progress_history.append(score)

        return min(score, 1.0)

    async def _decide_next_action(
        self, action_result: Optional[Any], progress_score: float
    ) -> Optional[str]:
        """
        Decide on the next action based on context.

        NO HARDCODED ACTIONS - uses context and heuristics.
        """
        # Get current perception
        perception = self.shared_memory.get(MemoryKey.PERCEPTION_RESULT, {})
        page_type = perception.get("page_type", "unknown")
        task = self.shared_memory.get(MemoryKey.TASK_DESCRIPTION, "")

        # Generate next action based on context
        if progress_score < 0.3:
            # Early stage - explore and find target
            if page_type == "unknown":
                return "Изучить страницу и понять как продвинуться к цели"
            return "Найти целевой элемент для взаимодействия"

        elif progress_score < 0.7:
            # Middle stage - interact with elements
            if page_type == "catalog":
                return "Найти нужный товар или категорию"
            elif page_type == "product":
                return "Добавить товар в корзину или выбрать опции"
            elif page_type == "cart":
                return "Перейти к оформлению заказа"
            return "Выполнить следующее действие для продвижения к цели"

        elif progress_score < 1.0:
            # Late stage - finalize
            if page_type == "checkout":
                return "Заполнить необходимые данные для оформления"
            return "Завершить выполнение задачи"

        else:
            # Task complete
            return None

    async def _generate_reasoning(
        self, action_result: Optional[Any], progress_made: bool
    ) -> str:
        """Generate reasoning for the reflection."""
        reasoning_parts = []

        # Action success
        if action_result:
            success = await self._evaluate_action_success(action_result)
            if success:
                reasoning_parts.append("Последнее действие выполнено успешно")
            else:
                reasoning_parts.append("Последнее действие не принесло результата")

        # Progress
        if progress_made:
            reasoning_parts.append("Прогресс в выполнении задачи есть")
        else:
            reasoning_parts.append("Прогресса нет, нужно попробовать другой подход")

        # Context
        perception = self.shared_memory.get(MemoryKey.PERCEPTION_RESULT, {})
        if perception.get("modal_detected"):
            reasoning_parts.append("Есть активное модальное окно, требующее внимания")

        return ". ".join(reasoning_parts) if reasoning_parts else "Продолжаю выполнение задачи"

    async def _identify_errors(self, action_result: Optional[Any]) -> List[str]:
        """Identify any errors that occurred."""
        errors = []

        if action_result:
            # Check for error attribute
            if hasattr(action_result, "error") and action_result.error:
                errors.append(action_result.error)

            # Check for error in dict
            if isinstance(action_result, dict):
                if action_result.get("error"):
                    errors.append(action_result["error"])
                if not action_result.get("success"):
                    errors.append("Действие не выполнено")

        # Check for stale state
        perception = self.shared_memory.get(MemoryKey.PERCEPTION_RESULT)
        if perception:
            url = self.shared_memory.get(MemoryKey.CURRENT_URL)
            if not url or url == "about:blank":
                errors.append("Нет активной страницы")

        return errors

    async def _generate_corrections(self, errors: List[str]) -> List[str]:
        """Generate suggested corrections for errors."""
        corrections = []

        for error in errors:
            error_lower = error.lower()

            if "not found" in error_lower or "не найден" in error_lower:
                corrections.append("Попробовать найти элемент по другим признакам")

            elif "timeout" in error_lower or "время" in error_lower:
                corrections.append("Подождать дольше или проверить загрузку страницы")

            elif "blocked" in error_lower or "заблокирован" in error_lower:
                corrections.append("Проверить модальные окна или перекрывающие элементы")

            else:
                corrections.append("Проанализировать ситуацию и попробовать альтернативный подход")

        return corrections

    async def _calculate_confidence(self, progress_score: float) -> float:
        """Calculate confidence in the current assessment."""
        # Higher progress = higher confidence
        # Add some uncertainty factor
        base_confidence = progress_score
        uncertainty = 0.1 if progress_score < 0.5 else 0.05
        return min(base_confidence + (1 - base_confidence) * 0.5, 1.0)

    async def should_continue(
        self, progress_score: float, errors: List[str]
    ) -> bool:
        """
        Decide if execution should continue.

        Returns:
            True if should continue, False if should stop
        """
        # Stop if task is complete
        if progress_score >= 1.0:
            return False

        # Continue if making progress
        if progress_score > 0:
            return True

        # Continue if no critical errors
        critical_errors = [e for e in errors if "fatal" in e.lower() or "крит" in e.lower()]
        if not critical_errors:
            return True

        # Default: continue
        return True

    async def analyze_error(self, error_info: Dict[str, Any]) -> None:
        """
        Analyze an error that occurred.

        Args:
            error_info: Information about the error
        """
        error_message = error_info.get("error", "Unknown error")
        self.log_error(f"Analyzing error: {error_message}")

        # Add to error history in shared memory
        error_history = self.shared_memory.get(MemoryKey.ERROR_HISTORY, [])
        error_history.append({
            "error": error_message,
            "timestamp": __import__("time").time(),
        })
        await self.shared_memory.set(MemoryKey.ERROR_HISTORY, error_history)

        # Generate and publish error analysis
        corrections = await self._generate_corrections([error_message])

        await self.send_message(
            MessageType.REFLECTION_ERROR_ANALYZED,
            {
                "error": error_message,
                "corrections": corrections,
            },
        )

    async def _update_progress_from_perception(self, perception: Dict[str, Any]) -> None:
        """Update progress based on new perception data."""
        # This can trigger a re-evaluation of progress
        pass

    def get_progress_summary(self) -> Dict[str, Any]:
        """Get summary of progress tracking."""
        return {
            "current_score": self._progress_history[-1] if self._progress_history else 0.0,
            "history": self._progress_history.copy(),
            "action_count": len(self._action_history),
        }

    async def _update_context_hints(
        self, reflection: ReflectionData, perception: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Обновить ContextHints с warnings и дополнительными наблюдениями.

        Получает существующий ContextHints от Perception Agent и добавляет warnings.
        """
        # Получить существующий ContextHints
        existing_hints_dict = self.shared_memory.get(MemoryKey.CONTEXT_HINTS)
        if existing_hints_dict:
            context_hints = ContextHints.from_dict(existing_hints_dict)
        else:
            context_hints = ContextHints()

        # Добавить warnings из reflection
        new_warnings = await self._generate_warnings(reflection, perception)
        for warning in new_warnings:
            if warning not in context_hints.warnings:
                context_hints.warnings.append(warning)

        # Обновить в shared memory
        await self.set_memory(MemoryKey.CONTEXT_HINTS, context_hints.to_dict())

    async def _generate_warnings(
        self, reflection: ReflectionData, perception: Optional[Dict[str, Any]]
    ) -> List[str]:
        """Сгенерировать warnings на основе reflection и perception."""
        warnings = []

        # Warning о checkout
        if perception:
            page_type = perception.get("page_type", "")
            if page_type == "checkout":
                warnings.append("Это страница оформления заказа")

        # Warning если есть ошибки
        if reflection.errors:
            warnings.append(f"Есть ошибки: {len(reflection.errors)}")

        # Warning если низкая уверенность
        if reflection.confidence < 0.5:
            warnings.append("Низкая уверенность в текущем состоянии")

        return warnings
