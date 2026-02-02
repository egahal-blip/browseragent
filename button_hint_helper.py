"""
Button Hint Helper — умный помощник для поиска кнопок действий.

Важно: Этот модуль НЕ хардкодит селекторы и НЕ говорит агенту "кликни на [X]".
Вместо этого он анализирует страницу и предоставляет контекстную информацию,
которая помогает агенту самостоятельно найти нужные кнопки.

Соответствует требованиям:
- ЗАПРЕЩЕНО: хардкод селекторов, прямые указания "кликни на элемент [X]"
- РАЗРЕШЕНО: умный анализ, эвристики, контекстные подсказки
"""

from typing import Optional, List, Dict, Any
from browser_use.browser.views import BrowserStateSummary
from browser_use.agent.views import AgentOutput
from browser_use.dom.views import EnhancedDOMTreeNode


class ButtonHintHelper:
    """
    Умный помощник для поиска кнопок действий на странице.

    Использует эвристики для анализа DOM и предоставляет контекстную
    информацию агенту, НЕ нарушая требования о запрете хардкода.
    """

    # Русские и английские ключевые слова для кнопок добавления в корзину
    CART_KEYWORDS = {
        'русский': [
            'корзин', 'в корз', 'вкорзин', 'купить', 'добавить',
            'в корзину', 'вкорзину', 'в карзину', 'вкарзину',
            'добавить в корзину', 'купить сейчас',
        ],
        'английский': [
            'cart', 'basket', 'add to cart', 'add to basket',
            'buy now', 'purchase', 'add', 'shop',
        ],
    }

    # Ключевые слова для кнопок оформления заказа
    CHECKOUT_KEYWORDS = {
        'русский': ['оформить', 'checkout', 'заказать', 'перейти к оплате'],
        'английский': ['checkout', 'place order', 'proceed to checkout'],
    }

    # Признаки иконок корзины (классы, aria-label, SVG)
    CART_ICON_PATTERNS = [
        'cart', 'basket', 'shopping', 'bag', 'trolley',
        'корзина', 'корзин', 'shop', 'store',
    ]

    # Символы добавления (+, ➕, ⊕ и т.д.)
    ADD_SYMBOLS = ['+', '＋', '➕', '⊕', '⨁', '⨀', 'plus', 'add', '＋']

    # SVG viewBox паттерны для иконок (стандартные размеры SVG иконок)
    SVG_ICON_VIEWBOX_PATTERNS = [
        '0 0 24 24',  # Самый распространённый размер Material Design
        '0 0 20 20',  # Fluent UI / современные иконки
        '0 0 16 16',
        '0 0 32 32',
        '0 0 48 48',
    ]

    # SVG aria-label паттерны для кнопок действий
    SVG_ACTION_ARIA_LABELS = [
        'add', 'plus', 'increase', 'increment',
        'remove', 'minus', 'decrease', 'decrement',
        'close', 'dismiss', 'cancel',
        'cart', 'basket', 'shopping',
        'expand', 'collapse', 'more', 'less',
    ]

    # Ключевые слова в className для кнопок действий
    ACTION_CLASS_PATTERNS = [
        'add', 'cart', 'buy', 'order', 'submit',
        'action', 'button', 'btn', 'control',
        'increase', 'decrease', 'quantity', 'qty',
        'plus', 'minus', 'remove',
    ]

    # Ключевые слова для кнопок с количеством (qty, quantity)
    QUANTITY_KEYWORDS = ['qty', 'quantity', 'колич', 'количество', 'amount']

    def __init__(self, debug: bool = True):
        """
        Args:
            debug: Выводить отладочную информацию
        """
        self.debug = debug
        self.step_count = 0
        self.hints_given = 0

    async def __call__(
        self,
        browser_state: BrowserStateSummary,
        agent_output: AgentOutput,
        step: int
    ) -> None:
        """
        Callback функция для browser-use.

        Анализирует страницу и предоставляет контекстные подсказки
        о кнопках действий.
        """
        self.step_count += 1

        # Анализируем страницу на предмет кнопок
        hints = self._analyze_buttons(browser_state)

        if hints and self.debug:
            self._log_button_hints(hints, browser_state.url)

    def _analyze_buttons(self, browser_state: BrowserStateSummary) -> Dict[str, Any]:
        """
        Анализирует страницу на предмет кнопок действий.

        Важно: НЕ возвращает индексы или селекторы!
        Возвращает только контекстную информацию.
        """
        result = {
            'cart_buttons': [],
            'checkout_buttons': [],
            'other_action_buttons': [],
        }

        if not browser_state.dom_state or not browser_state.dom_state.selector_map:
            return result

        # Анализируем каждый интерактивный элемент
        for index, enhanced_node in browser_state.dom_state.selector_map.items():
            button_info = self._analyze_element(enhanced_node)
            if button_info:
                if button_info['type'] == 'cart':
                    result['cart_buttons'].append(button_info)
                elif button_info['type'] == 'checkout':
                    result['checkout_buttons'].append(button_info)
                else:
                    result['other_action_buttons'].append(button_info)

        return result

    def _analyze_element(self, node: EnhancedDOMTreeNode) -> Optional[Dict[str, Any]]:
        """
        Анализирует отдельный элемент.

        Returns:
            Dict с информацией о кнопке или None
        """
        if not node or not node.attributes:
            return None

        attrs = node.attributes
        tag = node.tag_name if hasattr(node, 'tag_name') else ''

        # Собираем весь текст, связанный с элементом
        text_sources = []

        # Текст из ax_node
        if node.ax_node and node.ax_node.name:
            text_sources.append(node.ax_node.name.lower())

        # Текст из атрибутов
        for attr in ['aria-label', 'title', 'placeholder', 'value', 'alt', 'label']:
            if attr in attrs and attrs[attr]:
                text_sources.append(attrs[attr].lower())

        # Текст из class (для анализа паттернов)
        class_attr = attrs.get('class', '').lower()

        # ПРОВЕРКА 1: Кнопки по className с паттернами действий
        # Это важно для Самоката и подобных сайтов, где кнопки — div'ы с определенными классами
        for pattern in self.ACTION_CLASS_PATTERNS:
            if pattern in class_attr:
                # Дополнительная проверка — это кликабельный элемент
                if self._is_clickable_element(attrs, tag):
                    return {
                        'type': 'action_button',
                        'tag': tag,
                        'text': text_sources[0] if text_sources else '',
                        'class_pattern': pattern,
                        'has_icon': self._has_cart_icon(attrs),
                        'aria_label': attrs.get('aria-label', ''),
                    }

        # ПРОВЕРКА 2: SVG элементы (критично для Самоката и других сайтов!)
        # Если элемент сам является SVG
        is_svg_element = (
            tag == 'svg' or
            attrs.get('xmlns', '').startswith('http://www.w3.org/2000/svg') or
            'svg' in class_attr
        )

        if is_svg_element:
            # Проверяем viewBox — стандартный атрибут для SVG иконок
            viewbox = attrs.get('viewBox', attrs.get('viewbox', ''))
            is_icon_viewbox = any(pattern in viewbox for pattern in self.SVG_ICON_VIEWBOX_PATTERNS)

            # Проверяем aria-label на предмет действий
            aria_label = attrs.get('aria-label', '').lower()
            is_action_icon = any(pattern in aria_label for pattern in self.SVG_ACTION_ARIA_LABELS)

            # Если это SVG с иконкой — определяем тип действия
            if is_icon_viewbox or is_action_icon:
                button_type = 'svg_icon_button'
                text_desc = 'SVG иконка'

                # Уточняем тип по aria-label
                if any(word in aria_label for word in ['add', 'plus', 'increase', 'increment']):
                    button_type = 'svg_add_button'
                    text_desc = 'SVG иконка [добавить]'
                elif any(word in aria_label for word in ['remove', 'minus', 'decrease', 'decrement']):
                    button_type = 'svg_remove_button'
                    text_desc = 'SVG иконка [удалить]'
                elif any(word in aria_label for word in ['close', 'dismiss', 'cancel']):
                    button_type = 'svg_close_button'
                    text_desc = 'SVG иконка [закрыть]'
                elif any(word in aria_label for word in ['cart', 'basket', 'shopping']):
                    button_type = 'cart'
                    text_desc = 'SVG иконка корзины'

                return {
                    'type': button_type,
                    'tag': tag,
                    'text': text_desc,
                    'has_icon': True,
                    'aria_label': attrs.get('aria-label', ''),
                    'viewbox': viewbox,
                }

            # Даже без viewBox/aria — если это SVG с кликабельным родителем, это иконка
            if self._is_clickable_element(attrs, tag):
                return {
                    'type': 'svg_icon_button',
                    'tag': tag,
                    'text': 'SVG элемент (возможно иконка)',
                    'has_icon': True,
                    'aria_label': attrs.get('aria-label', ''),
                }

        # ПРОВЕРКА 3: Родительские элементы могут содержать SVG
        # Проверяем, есть ли у элемента указание на SVG внутри (через класс или атрибуты)
        if 'icon' in class_attr or 'svg' in class_attr:
            if self._is_clickable_element(attrs, tag):
                return {
                    'type': 'icon_button',
                    'tag': tag,
                    'text': text_sources[0] if text_sources else '',
                    'has_icon': True,
                    'aria_label': attrs.get('aria-label', ''),
                }

        # ПРОВЕРКА 4: Кнопки корзины
        for text in text_sources:
            for keyword in self.CART_KEYWORDS['русский'] + self.CART_KEYWORDS['английский']:
                if keyword in text:
                    return {
                        'type': 'cart',
                        'tag': tag,
                        'text': text,
                        'has_icon': self._has_cart_icon(attrs),
                        'aria_label': attrs.get('aria-label', ''),
                    }

        # ПРОВЕРКА 5: Иконки корзины (даже без текста)
        if self._has_cart_icon(attrs):
            if self._is_clickable_element(attrs, tag):
                return {
                    'type': 'cart',
                    'tag': tag,
                    'text': 'иконка корзины',
                    'has_icon': True,
                    'aria_label': attrs.get('aria-label', ''),
                }

        # ПРОВЕРКА 6: Кнопки с символами добавления (+, ➕, и т.д.)
        for text in text_sources:
            if text.strip() in self.ADD_SYMBOLS:
                return {
                    'type': 'add_button',
                    'tag': tag,
                    'text': text,
                    'has_icon': False,
                    'aria_label': attrs.get('aria-label', ''),
                }

            for symbol in self.ADD_SYMBOLS:
                if symbol in text.lower():
                    return {
                        'type': 'add_button',
                        'tag': tag,
                        'text': text,
                        'has_icon': False,
                        'aria_label': attrs.get('aria-label', ''),
                    }

        # ПРОВЕРКА 7: Кнопки с количеством (qty, quantity)
        for text in text_sources:
            for keyword in self.QUANTITY_KEYWORDS:
                if keyword in text.lower():
                    return {
                        'type': 'quantity_control',
                        'tag': tag,
                        'text': text,
                        'has_icon': False,
                        'aria_label': attrs.get('aria-label', ''),
                    }

        # ПРОВЕРКА 8: Кнопки оформления заказа
        for text in text_sources:
            for keyword in self.CHECKOUT_KEYWORDS['русский'] + self.CHECKOUT_KEYWORDS['английский']:
                if keyword in text:
                    return {
                        'type': 'checkout',
                        'tag': tag,
                        'text': text,
                        'has_icon': False,
                        'aria_label': attrs.get('aria-label', ''),
                    }

        return None

    def _has_cart_icon(self, attrs: Dict[str, str]) -> bool:
        """
        Проверяет, связан ли элемент с иконкой корзины.

        Использует эвристики, НЕ хардкодит селекторы!
        """
        if not attrs:
            return False

        # Проверяем aria-label
        aria_label = attrs.get('aria-label', '').lower()
        for pattern in self.CART_ICON_PATTERNS:
            if pattern in aria_label:
                return True

        # Проверяем class
        class_attr = attrs.get('class', '').lower()
        for pattern in self.CART_ICON_PATTERNS:
            if pattern in class_attr:
                return True

        # Проверяем data-атрибуты
        for key, value in attrs.items():
            if key.startswith('data-'):
                for pattern in self.CART_ICON_PATTERNS:
                    if pattern in value.lower():
                        return True

        return False

    def _is_clickable_element(self, attrs: Dict[str, str], tag: str) -> bool:
        """
        Проверяет, является ли элемент кликабельным.

        Это важно для распознавания div'ов и span'ов, которые ведут себя как кнопки.
        """
        if not attrs:
            return False

        # Явные признаки кнопки (расширенный список)
        if tag in ['button', 'a', 'span', 'div', 'td']:
            # Для span/div/div/td нужны дополнительные признаки
            if tag in ['button', 'a']:
                return True

        # role="button"
        if attrs.get('role') == 'button':
            return True

        # Классы, указывающие на кнопку
        class_attr = attrs.get('class', '').lower()
        if any(pattern in class_attr for pattern in ['button', 'btn', 'click', 'action', 'add', 'cart']):
            return True

        # Наличие onclick/onmousedown обработчика
        if attrs.get('onclick') or attrs.get('onmousedown'):
            return True

        # href для ссылок
        if attrs.get('href'):
            return True

        # data-action для SPA приложений
        if attrs.get('data-action') or attrs.get('data-goal'):
            return True

        # Курсор pointer в стиле (если есть)
        style = attrs.get('style', '').lower()
        if 'cursor: pointer' in style or 'cursor:pointer' in style:
            return True

        return False

    def _log_button_hints(self, hints: Dict[str, Any], url: str) -> None:
        """Выводит контекстные подсказки о кнопках."""
        if not hints:
            return

        has_hints = (
            hints['cart_buttons'] or
            hints['checkout_buttons'] or
            hints['other_action_buttons']
        )

        if not has_hints:
            return

        self.hints_given += 1

        print("\n" + "=" * 60)
        print("🔍 BUTTON HINT HELPER: Обнаружены потенциальные кнопки")
        print("=" * 60)
        print(f"URL: {url}")

        if hints['cart_buttons']:
            print(f"\n🛒 Кнопки добавления в корзину ({len(hints['cart_buttons'])}):")
            for btn in hints['cart_buttons'][:5]:
                icon_mark = " 🎨" if btn['has_icon'] else ""
                text_display = f"'{btn['text']}'" if btn['text'] else ''
                aria_display = f" ({btn['aria_label']})" if btn['aria_label'] else ''
                print(f"   - <{btn['tag']}>{icon_mark} {text_display}{aria_display}")

        if hints['checkout_buttons']:
            print(f"\n💳 Кнопки оформления заказа ({len(hints['checkout_buttons'])}):")
            for btn in hints['checkout_buttons'][:3]:
                text_display = f"'{btn['text']}'" if btn['text'] else ''
                print(f"   - <{btn['tag']}> {text_display}")

        # Отображаем кнопки с символами добавления (+, ➕) и SVG кнопки
        add_buttons = [btn for btn in hints['other_action_buttons'] if btn['type'] in [
            'add_button', 'quantity_control', 'svg_add_button', 'svg_remove_button',
            'svg_close_button', 'svg_icon_button', 'icon_button', 'action_button'
        ]]
        if add_buttons:
            print(f"\n➕ Кнопки добавления/управления ({len(add_buttons)}):")
            for btn in add_buttons[:8]:
                text_display = f"'{btn['text']}'" if btn['text'] else ''
                aria_display = f" ({btn['aria_label']})" if btn['aria_label'] else ''

                # Определяем отображение типа
                if btn['type'] == 'svg_add_button':
                    type_display = " [SVG +]"
                elif btn['type'] == 'svg_remove_button':
                    type_display = " [SVG -]"
                elif btn['type'] == 'svg_close_button':
                    type_display = " [SVG ×]"
                elif btn['type'] == 'svg_icon_button':
                    type_display = " [SVG иконка]"
                elif btn['type'] == 'icon_button':
                    type_display = " [иконка]"
                elif btn['type'] == 'action_button':
                    type_display = f" [{btn.get('class_pattern', 'действие')}]"
                elif btn['type'] == 'add_button':
                    type_display = " [добавить]"
                else:
                    type_display = " [количество]"

                print(f"   - <{btn['tag']}>{type_display} {text_display}{aria_display}")

        print("=" * 60)
        print("💡 Эти подсказки помогают агенту понять страницу.")
        print("   Агент САМ решает, на что кликнуть.")
        print("=" * 60)

    def get_stats(self) -> dict:
        """Возвращает статистику работы."""
        return {
            "steps": self.step_count,
            "hints_given": self.hints_given,
        }
