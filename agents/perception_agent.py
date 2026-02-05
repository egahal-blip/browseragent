"""
Perception Agent - Analyzes page state and detects patterns.

КРИТИЧЕСКИ ВАЖНО:
- NO хардкод селекторов
- NO жёстких инструкций
- Использовать эвристики и контекст
"""

import asyncio
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set
import logging

from agent_system.agent_base import AgentBase, AgentCapability, AgentConfig
from agent_system.agent_message import MessageType
from agent_system.shared_memory import (
    SharedMemory,
    MemoryKey,
    PerceptionData,
    ContextHints,
)

logger = logging.getLogger(__name__)


# Минималистичный системный промпт для Perception Agent
PERCEPTION_SYSTEM_PROMPT = """
Ты — агент восприятия для браузера.

Твоя задача — анализировать страницу и сообщать:
1. Тип страницы (каталог, товар, корзина, оформление заказа и т.д.)
2. Обнаруженные паттерны (модальные окна, пагинация, формы)
3. Интерактивные элементы (кнопки, ссылки, поля ввода)
4. Контекст (что можно сделать на этой странице)

Работай autonomously, делай выводы на основе контекста.
"""


class PerceptionAgent(AgentBase):
    """
    Agent for perceiving and analyzing browser state.

    Detects patterns and understands page context WITHOUT hardcoding selectors.
    """

    def __init__(
        self,
        event_bus,
        shared_memory: SharedMemory,
        llm: Any,
        debug: bool = False,
    ):
        config = AgentConfig(
            name="PerceptionAgent",
            capabilities={
                AgentCapability.PERCEPTION,
                AgentCapability.PATTERN_DETECTION,
                AgentCapability.DOM_ANALYSIS,
            },
            system_prompt=PERCEPTION_SYSTEM_PROMPT,
            debug=debug,
        )

        super().__init__(config, event_bus, shared_memory)
        self.llm = llm

        # Subscribe to relevant messages
        self._subscribe_to_messages()

    def _subscribe_to_messages(self) -> None:
        """Subscribe to relevant message types."""
        self.event_bus.subscribe(
            MessageType.ACTION_COMPLETED, self._on_action_completed
        )

    async def _on_action_completed(self, message) -> None:
        """Handle action completion by re-perceiving the page."""
        self.log_debug("Action completed, re-perceiving page")
        # Trigger perception update
        await self.process({"trigger": "action_completed"})

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process input and produce perception data.

        Args:
            input_data: Contains browser_state or other context

        Returns:
            Dictionary with perception results
        """
        browser_state = input_data.get("browser_state")

        if not browser_state:
            self.log_warning("No browser_state in input_data")
            return {"success": False, "error": "No browser state"}

        try:
            # Analyze the page
            perception = await self.perceive_page(browser_state)

            # Detect patterns
            patterns = await self.detect_patterns(browser_state)

            # Combine into perception data
            perception_data = PerceptionData(
                page_type=perception.get("page_type"),
                patterns=patterns,
                interactive_elements=perception.get("interactive_elements", []),
                modal_detected=perception.get("modal_detected", False),
                pagination_detected=perception.get("pagination_detected", False),
                forms_detected=perception.get("forms_detected", []),
                confidence=perception.get("confidence", 0.5),
                observations=perception.get("observations", []),
            )

            # Store in shared memory
            await self.set_memory(MemoryKey.PERCEPTION_RESULT, perception_data.to_dict())
            await self.set_memory(MemoryKey.CURRENT_URL, browser_state.get("url", ""))
            await self.set_memory(MemoryKey.PAGE_TITLE, browser_state.get("title", ""))

            # Generate ContextHints for injection into prompt
            context_hints = self._generate_context_hints(perception_data, patterns)
            await self.set_memory(MemoryKey.CONTEXT_HINTS, context_hints.to_dict())

            # Publish perception result
            await self.send_message(
                MessageType.PERCEPTION_PAGE_ANALYZED,
                perception_data.to_dict(),
            )

            # Publish detected patterns
            if patterns:
                await self.send_message(
                    MessageType.PERCEPTION_PATTERN_DETECTED,
                    {"patterns": patterns},
                )

            self.log_info(f"Page perceived: {perception_data.page_type}")

            return {
                "success": True,
                "perception": perception_data.to_dict(),
            }

        except Exception as e:
            self.log_error(f"Error in process: {e}")
            return {"success": False, "error": str(e)}

    async def perceive_page(self, browser_state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze the current page state.

        Args:
            browser_state: Current browser state

        Returns:
            Dictionary with page analysis
        """
        result = {
            "page_type": None,
            "interactive_elements": [],
            "modal_detected": False,
            "pagination_detected": False,
            "forms_detected": [],
            "observations": [],
            "confidence": 0.5,
        }

        # Get URL and title for context
        url = browser_state.get("url", "")
        title = browser_state.get("title", "")

        # Detect page type from URL and content (NO HARDCODED SELECTORS)
        page_type = await self._detect_page_type(url, title, browser_state)
        result["page_type"] = page_type

        # Extract interactive elements
        result["interactive_elements"] = await self._extract_interactive_elements(browser_state)

        # Detect patterns
        result["modal_detected"] = await self._detect_modal(browser_state)
        result["pagination_detected"] = await self._detect_pagination(browser_state)
        result["forms_detected"] = await self._detect_forms(browser_state)

        # Generate observations
        result["observations"] = await self._generate_observations(result, url, title)

        return result

    async def _detect_page_type(
        self, url: str, title: str, browser_state: Dict[str, Any]
    ) -> str:
        """
        Detect page type from context (NO HARDCODED SELECTORS).

        Uses heuristics based on URL structure, title, and page content.
        """
        url_lower = url.lower()
        title_lower = title.lower()

        # Get text content from page
        page_text = self._extract_text_content(browser_state).lower()

        # Analyze URL patterns
        url_indicators = {
            "catalog": ["/catalog", "/category", "/products", "/shop", "/store"],
            "product": ["/product", "/item", "/p/"],
            "cart": ["/cart", "/basket", "/bag"],
            "checkout": ["/checkout", "/order", "/payment"],
            "search": ["/search", "/find", "/q="],
            "profile": ["/profile", "/account", "/settings"],
            "login": ["/login", "/signin", "/auth"],
        }

        # Check URL patterns
        for page_type, patterns in url_indicators.items():
            if any(pattern in url_lower for pattern in patterns):
                return page_type

        # Analyze title and page text
        text_indicators = {
            "cart": ["cart", "basket", "your items", "shopping cart", "korzina", "корзина"],
            "checkout": ["checkout", "payment", "shipping", "оформление", "оплата"],
            "product": ["buy", "purchase", "add to", "добавить в корзину"],
            "catalog": ["catalog", "products", "categories", "каталог"],
        }

        # Combine title and page text
        combined_text = title_lower + " " + page_text

        # Check for strongest indicators first
        for page_type, keywords in text_indicators.items():
            if any(keyword in combined_text for keyword in keywords):
                # Count matches for confidence
                matches = sum(1 for kw in keywords if kw in combined_text)
                if matches >= 2:  # Need at least 2 matches for confidence
                    return page_type

        # Default: unknown
        return "unknown"

    def _extract_text_content(self, browser_state: Dict[str, Any]) -> str:
        """Extract text content from browser state."""
        texts = []

        # From interactive elements
        for elem in browser_state.get("clickable_elements", []):
            if "text" in elem and elem["text"]:
                texts.append(elem["text"])

        return " ".join(texts)

    async def _extract_interactive_elements(
        self, browser_state: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Extract and categorize interactive elements."""
        elements = []

        for elem in browser_state.get("clickable_elements", []):
            elem_info = {
                "index": elem.get("index"),
                "tag_name": elem.get("tag_name", ""),
                "text": elem.get("text", ""),
                "attributes": elem.get("attributes", {}),
            }

            # Categorize by heuristics (NO HARDCODED SELECTORS)
            elem_info["category"] = self._categorize_element(elem_info)

            elements.append(elem_info)

        return elements

    def _categorize_element(self, elem: Dict[str, Any]) -> str:
        """
        Categorize element using heuristics.

        NO HARDCODED SELECTORS - uses patterns and context.
        """
        text = elem.get("text", "").lower()
        attrs = elem.get("attributes", {})
        tag = elem.get("tag_name", "").lower()
        classes = attrs.get("class", "").lower()

        # Button indicators
        button_indicators = ["button", "btn", "click", "tap", "нажать"]
        if tag == "button" or any(ind in classes for ind in button_indicators):
            return "button"

        # Link indicators
        if tag == "a" or attrs.get("href"):
            return "link"

        # Input indicators
        if tag in ["input", "textarea", "select"]:
            return "input"

        # Action indicators (add to cart, buy, etc.)
        action_keywords = [
            "add", "buy", "purchase", "order", "cart",
            "добавить", "купить", "заказать", "в корзину",
        ]
        if any(kw in text for kw in action_keywords):
            return "action_button"

        # Navigation indicators
        nav_keywords = ["next", "prev", "back", "forward", "menu", "далее", "назад"]
        if any(kw in text for kw in nav_keywords):
            return "navigation"

        return "unknown"

    async def _detect_modal(self, browser_state: Dict[str, Any]) -> bool:
        """
        Detect modal windows (NO HARDCODED SELECTORS).

        Uses semantic HTML attributes and patterns.
        """
        # Check for modal indicators in browser state
        if browser_state.get("is_modal_present"):
            return True

        # Look for modal patterns in elements
        for elem in browser_state.get("clickable_elements", []):
            attrs = elem.get("attributes", {})
            classes = attrs.get("class", "").lower()

            # Semantic HTML
            if attrs.get("role") == "dialog":
                return True
            if attrs.get("aria-modal") == "true":
                return True

            # Common class patterns
            modal_patterns = ["modal", "dialog", "popup", "overlay", "lightbox"]
            if any(pattern in classes for pattern in modal_patterns):
                return True

        return False

    async def _detect_pagination(self, browser_state: Dict[str, Any]) -> bool:
        """
        Detect pagination (NO HARDCODED SELECTORS).

        Uses text patterns and element context.
        """
        # Look for pagination indicators in elements
        for elem in browser_state.get("clickable_elements", []):
            text = elem.get("text", "").lower()
            attrs = elem.get("attributes", {})
            classes = attrs.get("class", "").lower()

            # Common pagination patterns
            pagination_keywords = [
                "next", "prev", "previous", "page", "показать ещё",
                "load more", "следующая", "предыдущая",
            ]

            if any(kw in text for kw in pagination_keywords):
                return True

            if "pagin" in classes:  # pagination, paginate, etc.
                return True

        return False

    async def _detect_forms(self, browser_state: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Detect forms on the page."""
        forms = []

        for elem in browser_state.get("input_elements", []):
            forms.append({
                "tag": elem.get("tag_name"),
                "type": elem.get("input_type", "text"),
                "name": elem.get("name", ""),
                "placeholder": elem.get("placeholder", ""),
            })

        return forms

    async def _generate_observations(
        self, perception: Dict[str, Any], url: str, title: str
    ) -> List[str]:
        """Generate natural language observations."""
        observations = []

        # Page type observation
        page_type = perception.get("page_type", "unknown")
        if page_type != "unknown":
            observations.append(f"Это страница типа: {page_type}")

        # Modal observation
        if perception.get("modal_detected"):
            observations.append("На странице открыто модальное окно")

        # Pagination observation
        if perception.get("pagination_detected"):
            observations.append("На странице есть пагинация")

        # Forms observation
        forms = perception.get("forms_detected", [])
        if forms:
            observations.append(f"На странице {len(forms)} форм(ы) для ввода")

        # Interactive elements count
        elements = perception.get("interactive_elements", [])
        if elements:
            buttons = [e for e in elements if e.get("category") == "button"]
            if buttons:
                observations.append(f"Обнаружено {len(buttons)} кнопок")

        return observations

    async def detect_patterns(self, browser_state: Dict[str, Any]) -> List[str]:
        """
        Detect patterns on the page (NO HARDCODED SELECTORS).

        Returns list of detected patterns.
        """
        patterns = []

        # Check for common patterns
        if await self._detect_modal(browser_state):
            patterns.append("modal_window")

        if await self._detect_pagination(browser_state):
            patterns.append("pagination")

        forms = await self._detect_forms(browser_state)
        if forms:
            patterns.append(f"forms ({len(forms)} found)")

        # Detect shopping-specific patterns
        page_text = self._extract_text_content(browser_state).lower()
        cart_keywords = ["cart", "basket", "корзина"]
        if any(kw in page_text for kw in cart_keywords):
            patterns.append("shopping_cart_present")

        checkout_keywords = ["checkout", "payment", "оформление", "оплата"]
        if any(kw in page_text for kw in checkout_keywords):
            patterns.append("checkout_flow")

        # Detect quantity controls (+/- buttons)
        if await self._detect_quantity_controls(browser_state):
            patterns.append("quantity_controls_detected")

        return patterns

    async def _detect_quantity_controls(self, browser_state: Dict[str, Any]) -> bool:
        """
        Detect quantity controls (+/- buttons, increase/decrease).

        Это наблюдение, а не инструкция! Агент сам решает как использовать.
        """
        for elem in browser_state.get("clickable_elements", []):
            text = elem.get("text", "").lower()
            attrs = elem.get("attributes", {})
            aria_label = attrs.get("aria-label", "").lower()
            classes = attrs.get("class", "").lower()

            # Quantity control indicators (эвристики, не хардкод!)
            quantity_indicators = [
                "increase", "decrease", "increment", "decrement",
                "увеличить", "уменьшить", "плюс", "минус",
                "quantity", "qty", "count", "количество",
            ]

            # Check text and aria-label
            if any(ind in text for ind in quantity_indicators):
                return True
            if any(ind in aria_label for ind in quantity_indicators):
                return True

            # Check for common quantity control class patterns
            quantity_class_patterns = [
                "quantity", "qty", "counter", "stepper",
                "amount", "number-spinner", "qty-selector",
            ]
            if any(pattern in classes for pattern in quantity_class_patterns):
                return True

            # Check for symbol buttons (+, -) but exclude navigation
            if text.strip() in ["+", "-", "+]", "[-", "(+)", "(-)"]:
                # Verify it's not just a navigation button
                if not any(nav in classes for nav in ["nav", "menu", "pagination"]):
                    return True

        return False

    def _generate_context_hints(
        self, perception_data: PerceptionData, patterns: List[str]
    ) -> ContextHints:
        """
        Сгенерировать ContextHints для инъекции в промпт browser-use Agent.

        БЕЗ жёстких инструкций - только наблюдения и паттерны!
        """
        from agent_system.shared_memory import ContextHints

        # Observations из perception_data
        observations = list(perception_data.observations)

        # Добавляем наблюдение о типе страницы
        if perception_data.page_type and perception_data.page_type != "unknown":
            obs = f"Тип страницы: {perception_data.page_type}"
            if obs not in observations:
                observations.insert(0, obs)

        # Добавляем наблюдение о quantity controls (НЕ инструкция, только факт!)
        if "quantity_controls_detected" in patterns:
            obs = "На странице есть элементы управления количеством товара (+/- кнопки)"
            if obs not in observations:
                observations.append(obs)

        # Suggested categories на основе интерактивных элементов
        suggested_categories = set()
        for elem in perception_data.interactive_elements:
            category = elem.get("category", "")
            if category and category != "unknown":
                suggested_categories.add(category)

        # Warnings пока пустые (Reflection Agent добавит при необходимости)
        warnings = []

        return ContextHints(
            observations=observations,
            patterns=patterns,
            warnings=warnings,
            suggested_categories=list(suggested_categories),
        )
