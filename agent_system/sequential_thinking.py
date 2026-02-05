"""
Sequential Thinking Engine - Implements step-by-step reasoning.

This module provides the sequential thinking pattern where agents
reason step by step: thought -> observation -> action -> reflection.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import logging

from .shared_memory import (
    SharedMemory,
    MemoryKey,
    ThoughtStep,
)

logger = logging.getLogger(__name__)


@dataclass
class ThinkingContext:
    """Context for sequential thinking."""

    task: str
    current_step: int = 0
    max_steps: int = 25
    thought_chain: List[ThoughtStep] = field(default_factory=list)
    completed: bool = False
    error_count: int = 0
    max_errors: int = 3

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task": self.task,
            "current_step": self.current_step,
            "max_steps": self.max_steps,
            "thought_chain": [t.to_dict() for t in self.thought_chain],
            "completed": self.completed,
            "error_count": self.error_count,
        }


class SequentialThinkingEngine:
    """
    Engine for sequential thinking pattern.

    Coordinates the flow: Thought -> Observation -> Reasoning -> Action -> Reflection
    """

    def __init__(
        self,
        shared_memory: SharedMemory,
        max_steps: int = 25,
        max_errors: int = 3,
        debug: bool = False,
    ):
        self.shared_memory = shared_memory
        self.max_steps = max_steps
        self.max_errors = max_errors
        self.debug = debug
        self._logger = logging.getLogger("SequentialThinking")

        if debug:
            self._logger.setLevel(logging.DEBUG)

    async def create_thinking_context(self, task: str) -> ThinkingContext:
        """Create a new thinking context for a task."""
        context = ThinkingContext(
            task=task,
            max_steps=self.max_steps,
            max_errors=self.max_errors,
        )

        # Store in shared memory
        await self.shared_memory.set(MemoryKey.TASK_DESCRIPTION, task)
        await self.shared_memory.set(MemoryKey.THOUGHT_CHAIN, context.thought_chain)

        return context

    async def think_step(
        self,
        context: ThinkingContext,
        perception: Any,
        previous_result: Optional[Any] = None,
    ) -> ThoughtStep:
        """
        Execute one step of sequential thinking.

        Args:
            context: Current thinking context
            perception: Current perception of the page/state
            previous_result: Result of previous action (if any)

        Returns:
            ThoughtStep with the current thinking
        """
        step_num = context.current_step + 1

        # Build thought step components
        thought = await self._generate_thought(context, perception, previous_result)
        observation = await self._generate_observation(perception)
        action = await self._decide_action(context, thought, observation)
        reflection = await self._generate_reflection(context, previous_result) if previous_result else None
        next_thought = await self._plan_next_thought(context, action, reflection)

        thought_step = ThoughtStep(
            step_number=step_num,
            thought=thought,
            observation=observation,
            action=action,
            reflection=reflection,
            next_thought=next_thought,
        )

        # Add to chain
        context.thought_chain.append(thought_step)
        context.current_step = step_num

        # Update shared memory
        await self.shared_memory.set(MemoryKey.THOUGHT_CHAIN, context.thought_chain)
        await self.shared_memory.set(MemoryKey.NEXT_STEP, action)

        return thought_step

    async def should_continue(self, context: ThinkingContext) -> bool:
        """Decide if thinking should continue."""
        # Check max steps
        if context.current_step >= context.max_steps:
            self._logger.info(f"Reached max steps ({self.max_steps})")
            return False

        # Check error count
        if context.error_count >= context.max_errors:
            self._logger.warning(f"Reached max errors ({self.max_errors})")
            return False

        # Check if completed
        if context.completed:
            self._logger.info("Task marked as completed")
            return False

        return True

    async def _generate_thought(
        self,
        context: ThinkingContext,
        perception: Any,
        previous_result: Optional[Any],
    ) -> str:
        """
        Generate the current thought.

        This analyzes the current situation and formulates understanding.
        """
        # Get context from shared memory
        task = await self.shared_memory.get(MemoryKey.TASK_DESCRIPTION)
        url = await self.shared_memory.get(MemoryKey.CURRENT_URL)

        thought_parts = []

        # What I'm trying to do
        if context.current_step == 0:
            thought_parts.append(f"Мне нужно выполнить задачу: {task}")
        else:
            thought_parts.append(f"Продолжаю выполнение задачи: {task}")

        # Current situation
        if url:
            thought_parts.append(f"Сейчас я на странице: {url}")

        # Analyze previous result
        if previous_result:
            if hasattr(previous_result, "success"):
                if previous_result.success:
                    thought_parts.append("Предыдущее действие выполнено успешно")
                else:
                    thought_parts.append(f"Предыдущее действие не удалось: {previous_result.error}")
                    context.error_count += 1

        # Current page context
        if hasattr(perception, "page_type") and perception.page_type:
            thought_parts.append(f"Тип страницы: {perception.page_type}")

        if hasattr(perception, "observations") and perception.observations:
            thought_parts.append(f"Наблюдения: {', '.join(perception.observations[:3])}")

        return ". ".join(thought_parts) + "."

    async def _generate_observation(self, perception: Any) -> str:
        """
        Generate observation from current perception.

        This describes what is currently visible/observable.
        """
        observations = []

        # Basic page info
        if hasattr(perception, "page_type"):
            observations.append(f"Тип страницы: {perception.page_type or 'неизвестно'}")

        # Patterns detected
        if hasattr(perception, "patterns") and perception.patterns:
            observations.append(f"Обнаружены паттерны: {', '.join(perception.patterns)}")

        # Interactive elements
        if hasattr(perception, "interactive_elements"):
            count = len(perception.interactive_elements)
            observations.append(f"Интерактивных элементов: {count}")

        # Modal detection
        if hasattr(perception, "modal_detected") and perception.modal_detected:
            observations.append("Обнаружено модальное окно")

        # Pagination
        if hasattr(perception, "pagination_detected") and perception.pagination_detected:
            observations.append("Обнаружена пагинация")

        # Forms
        if hasattr(perception, "forms_detected") and perception.forms_detected:
            count = len(perception.forms_detected)
            observations.append(f"Форм на странице: {count}")

        return ". ".join(observations) if observations else "Страница загружена"

    async def _decide_action(
        self,
        context: ThinkingContext,
        thought: str,
        observation: str,
    ) -> str:
        """
        Decide on the next action based on thought and observation.

        This is where the agent decides what to do next.
        """
        # Get current plan if exists
        plan = await self.shared_memory.get(MemoryKey.CURRENT_PLAN)

        if plan and isinstance(plan, list) and context.current_step <= len(plan):
            # Follow existing plan
            planned_action = plan[context.current_step - 1] if context.current_step > 0 else plan[0]
            return f"Выполнить запланированное действие: {planned_action}"

        # Determine action based on context
        action_parts = []

        # Check if there's a modal
        is_modal = await self.shared_memory.get(MemoryKey.PERCEPTION_RESULT, {}).get("modal_detected", False)
        if is_modal:
            action_parts.append("Взаимодействовать с модальным окном")

        # Check task progress
        progress = await self.shared_memory.get(MemoryKey.PROGRESS_SCORE, 0.0)
        if progress < 0.3:
            action_parts.append("Изучить страницу и найти целевые элементы")
        elif progress < 0.7:
            action_parts.append("Выполнить необходимые действия для продвижения к цели")
        elif progress < 1.0:
            action_parts.append("Завершить выполнение задачи")

        return ". ".join(action_parts) if action_parts else "Продолжить исследование страницы"

    async def _generate_reflection(
        self,
        context: ThinkingContext,
        previous_result: Optional[Any],
    ) -> Optional[str]:
        """
        Generate reflection on previous action.

        This evaluates what happened and learns from it.
        """
        if not previous_result:
            return None

        reflections = []

        if hasattr(previous_result, "success"):
            if previous_result.success:
                reflections.append("Действие было успешным")
            else:
                reflections.append(f"Действие не удалось: {previous_result.error}")

        # Check if we made progress
        progress = await self.shared_memory.get(MemoryKey.PROGRESS_SCORE, 0.0)
        reflections.append(f"Прогресс выполнения: {progress * 100:.0f}%")

        return ". ".join(reflections) if reflections else None

    async def _plan_next_thought(
        self,
        context: ThinkingContext,
        action: str,
        reflection: Optional[str],
    ) -> Optional[str]:
        """
        Plan what comes next.

        This anticipates the next step in the process.
        """
        progress = await self.shared_memory.get(MemoryKey.PROGRESS_SCORE, 0.0)

        if progress >= 1.0:
            context.completed = True
            return "Задача выполнена"

        # Check if we need to correct course
        if reflection and "не удалось" in reflection.lower():
            return "Анализирую ошибку и пробую другой подход"

        return "Выполняю действие и анализирую результат"

    async def get_summary(self, context: ThinkingContext) -> Dict[str, Any]:
        """Get a summary of the thinking process."""
        return {
            "task": context.task,
            "steps_completed": context.current_step,
            "errors": context.error_count,
            "completed": context.completed,
            "last_action": context.thought_chain[-1].action if context.thought_chain else None,
        }
