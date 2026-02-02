"""
Security Layer — перехватывает опасные действия перед выполнением.

Интегрируется через register_new_step_callback в browser-use.
"""

from typing import Optional
from browser_use.browser.views import BrowserStateSummary
from browser_use.agent.views import AgentOutput


class SecurityLayer:
    """
    Security Layer — анализирует планируемые действия и блокирует опасные.

    Работает как callback для register_new_step_callback в Agent.
    """

    def __init__(self, auto_allow_safe: bool = True, debug: bool = False):
        """
        Args:
            auto_allow_safe: Автоматически разрешать безопасные действия
            debug: Выводить отладочную информацию о каждом шаге
        """
        self.auto_allow_safe = auto_allow_safe
        self.debug = debug
        self.blocked_count = 0
        self.allowed_count = 0
        self.step_count = 0

        # Опасные ключевые слова (только финальные действия оплаты)
        self.dangerous_keywords = {
            # Финальное подтверждение оплаты
            "confirm payment",
            "complete purchase",
            "pay now",
            "submit payment",
            "place order and pay",
            "pay with card",
            "pay with",
            # Checkout и оформление заказа (блокируем более агрессивно)
            "checkout",
            "place order",
            "proceed to checkout",
            "go to checkout",
            "continue to checkout",
            "оформить заказ",
            "оформить",
            "перейти к оформлению",
            "перейти к оплате",
            # Кнопки оплаты
            "оплатить",
            "оплату",
            "кнопка оплатить",
            "payment button",
            "pay button",
            # Банковские данные
            "enter card number",
            "enter cvv",
            "enter expiry",
            "card number",
            "card details",
            # Новые вкладки
            "open in new tab",
            "open in new window",
            "new tab",
            # Удаление
            "delete account",
            "remove account",
        }

        # Безопасные контексты — эти действия разрешены
        self.safe_contexts = {
            "select", "choose", "option", "size", "sauce", "topping",
            "add to cart", "add item", "add to basket", "add to",
            "continue shopping", "view cart", "view basket",
            "select size", "select option", "choose size"
        }

        # Опасные паттерны URL (блокируем checkout и оплату)
        self.dangerous_url_patterns = {
            "/payment/confirm",
            "/payment/submit",
            "/order/complete",
            "/checkout/success",
            "/pay",
            "/checkout",
            "/cart/checkout",
            "/order/checkout",
            "/ordering",
            "/оформить",
            "/оплата",
            "/basket/checkout",
            # Паттерны для российских сервисов доставки
            "checkout",
            "ordering",
            "payment",
            "pay",
        }

    async def __call__(
        self,
        browser_state: BrowserStateSummary,
        agent_output: AgentOutput,
        step: int
    ) -> None:
        """
        Callback функция для browser-use.

        Вызывается перед каждым шагом агента. Может прервать выполнение
        через исключение, но browser-use не поддерживает модификацию actions.

        Args:
            browser_state: Текущее состояние браузера
            agent_output: Что агент планирует сделать
            step: Номер шага
        """
        self.step_count += 1

        # Проверяем URL — если это страница оплаты, СРАЗУ блокируем
        current_url = browser_state.url.lower()
        for pattern in self.dangerous_url_patterns:
            if pattern in current_url:
                self.blocked_count += 1
                print("\n" + "=" * 60)
                print("🔒 SECURITY LAYER: Попытка перейти на страницу оплаты")
                print("=" * 60)
                print(f"URL: {browser_state.url}")
                print(f"Обнаружен паттерн: {pattern}")
                print("=" * 60)
                raise SecurityLayerBlockedAction(
                    f"Переход на страницу оплаты заблокирован: {browser_state.url}"
                )

        # Анализируем планируемые действия
        actions = agent_output.action if agent_output.action else []

        for action in actions:
            action_text = str(action).lower()

            # Блокируем переключение между вкладками — это значит что открылась новая вкладка
            if "switch_tab" in action_text or "switchtab" in action_text:
                self.blocked_count += 1
                print("\n" + "=" * 60)
                print("🔒 SECURITY LAYER: Попытка переключиться на новую вкладку")
                print("=" * 60)
                print(f"Действие: {action}")
                print(f"URL: {browser_state.url}")
                print("=" * 60)
                print("❌ Агент запрещено открывать или переключаться на новые вкладки!")
                raise SecurityLayerBlockedAction(
                    f"Переключение вкладок заблокировано: {action}"
                )

            # Отладочный вывод
            if self.debug:
                print(f"[Security Layer Step {self.step_count}] {action_text[:100]}...")

            # Дополнительная проверка: клик по элементу с текстом checkout/оплатить
            if "click" in action_text:
                # Проверяем есть ли в действии текст кнопки
                for dangerous in ["оплатить", "checkout", "place order", "оформить заказ", "pay now"]:
                    if dangerous in action_text:
                        self.blocked_count += 1
                        print("\n" + "=" * 60)
                        print("🔒 SECURITY LAYER: Попытка нажать кнопку оплаты/оформления")
                        print("=" * 60)
                        print(f"Действие: {action}")
                        print(f"URL: {browser_state.url}")
                        print(f"Обнаружен текст: {dangerous}")
                        print("=" * 60)
                        raise SecurityLayerBlockedAction(
                            f"Клик по кнопке '{dangerous}' заблокирован: {action}"
                        )

            # Проверяем на опасные ключевые слова
            if self._is_dangerous(action_text):
                # Но сначала проверяем безопасный контекст
                if self._is_safe_context(action_text):
                    if self.debug:
                        print(f"  ✓ Разрешено (безопасный контекст)")
                    self.allowed_count += 1
                    continue

                self.blocked_count += 1
                print("\n" + "=" * 60)
                print("🔒 SECURITY LAYER: Обнаружено опасное действие")
                print("=" * 60)
                print(f"Действие: {action}")
                print(f"URL: {browser_state.url}")
                print(f"Шаг: {step}")
                print("=" * 60)

                # Блокируем через исключение
                raise SecurityLayerBlockedAction(
                    f"Действие заблокировано Security Layer: {action}"
                )

        self.allowed_count += 1

    def _is_dangerous(self, action_text: str) -> bool:
        """Проверяет, содержит ли действие опасные ключевые слова."""
        return any(keyword in action_text for keyword in self.dangerous_keywords)

    def _is_safe_context(self, action_text: str) -> bool:
        """Проверяет, находится ли действие в безопасном контексте."""
        return any(safe_word in action_text for safe_word in self.safe_contexts)

    def get_stats(self) -> dict:
        """Возвращает статистику работы."""
        return {
            "steps": self.step_count,
            "allowed": self.allowed_count,
            "blocked": self.blocked_count,
            "total": self.allowed_count + self.blocked_count
        }


class SecurityLayerBlockedAction(Exception):
    """Исключение для блокировки опасного действия."""
    pass
