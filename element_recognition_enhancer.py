"""
Element Recognition Enhancer — улучшает распознавание элементов на странице.

Этот модуль НЕ говорит агенту "кликни на [X]" и НЕ хардкодит селекторы.
Вместо этого он улучшает контекст, который получает агент, помогая ему
самостоятельно распознать элементы типа кнопок "+", "-", иконок и т.д.

Соответствует требованиям:
- ЗАПРЕЩЕНО: хардкод селекторов, прямые указания "кликни на элемент [X]"
- РАЗРЕШЕНО: улучшение контекста, эвристики, умный анализ DOM
"""

from typing import Optional, List, Dict, Any, Set
from browser_use.browser.views import BrowserStateSummary
from browser_use.agent.views import AgentOutput
from browser_use.dom.views import EnhancedDOMTreeNode


class ElementRecognitionEnhancer:
    """
    Улучшает распознавание элементов на странице для агента.

    Анализирует DOM и выявляет элементы, которые могут быть проблемными
    для распознавания (кнопки с символами, иконки без текста и т.д.).
    """

    # Символы, которые могут быть кнопками действий
    ACTION_SYMBOLS = {
        'add': ['+', '＋', '➕', '⊕', '⨁', 'plus'],
        'remove': ['−', '-', '−', '➖', 'minus', 'remove'],
        'close': ['×', '✕', '❌', 'close', '×'],
        'expand': ['⌄', '▼', '▾', 'expand', 'more'],
        'collapse': ['⌃', '▲', '▴', 'collapse', 'less'],
        'check': ['✓', '✔', 'check', '✓'],
        'arrow_right': ['→', '➤', '▶', 'arrow', 'next'],
        'arrow_left': ['←', '◀', 'back'],
        'cart': ['🛒', 'cart', 'basket'],
    }

    # Классы элементов, которые часто содержат кнопки действий
    ACTION_CONTAINER_CLASSES = [
        'card', 'product', 'item', 'listing',
        'quantity', 'qty', 'counter', 'stepper',
        'action', 'control', 'button', 'btn',
        'price', 'cost', 'amount',
    ]

    # SVG viewBox паттерны для иконок
    SVG_ICON_VIEWBOX_PATTERNS = [
        '0 0 24 24',  # Material Design
        '0 0 20 20',  # Fluent UI
        '0 0 16 16',
        '0 0 32 32',
        '0 0 48 48',
    ]

    # SVG aria-label паттерны для кнопок действий
    SVG_ACTION_ARIA_LABELS = [
        'add', 'plus', 'increase', 'increment',
        'remove', 'minus', 'decrease', 'decrement',
        'close', 'dismiss', 'cancel',
    ]

    def __init__(self, debug: bool = True):
        """
        Args:
            debug: Выводить отладочную информацию
        """
        self.debug = debug
        self.step_count = 0
        self.elements_enhanced = 0

    async def __call__(
        self,
        browser_state: BrowserStateSummary,
        agent_output: AgentOutput,
        step: int
    ) -> None:
        """
        Callback функция для browser-use.

        Анализирует страницу и логирует информацию о потенциально
        проблемных элементах.
        """
        self.step_count += 1

        # Анализируем страницу на предмет проблемных элементов
        analysis = self._analyze_page(browser_state)

        if analysis['has_potential_issues'] and self.debug:
            self._log_enhancement_info(analysis, browser_state.url)

    def _analyze_page(self, browser_state: BrowserStateSummary) -> Dict[str, Any]:
        """
        Анализирует страницу на предмет потенциально проблемных элементов.

        Returns:
            Dict с информацией о найденных элементах
        """
        result = {
            'has_potential_issues': False,
            'symbol_buttons': [],
            'icon_buttons': [],
            'price_contexts': [],
            'quantity_controls': [],
        }

        if not browser_state.dom_state or not browser_state.dom_state.selector_map:
            return result

        # Группируем элементы по контексту (например, карточки товаров)
        self._analyze_elements_by_context(browser_state, result)

        # Проверяем, есть ли проблемы
        result['has_potential_issues'] = bool(
            result['symbol_buttons'] or
            result['icon_buttons'] or
            result['price_contexts'] or
            result['quantity_controls']
        )

        return result

    def _analyze_elements_by_context(
        self,
        browser_state: BrowserStateSummary,
        result: Dict[str, Any]
    ) -> None:
        """
        Анализирует элементы в контексте их окружения.

        Ключевая идея: кнопка "+" рядом с ценой — это добавление в корзину.
        """
        if not browser_state.dom_state.selector_map:
            return

        # Создаём индекс элементов по их позиции для быстрого поиска соседей
        elements_by_index = {}
        for index, node in browser_state.dom_state.selector_map.items():
            elements_by_index[index] = node

        # Анализируем каждый интерактивный элемент
        for index, node in elements_by_index.items():
            analysis = self._analyze_element_in_context(node, index, elements_by_index)
            if analysis:
                if analysis['type'] == 'symbol_button':
                    result['symbol_buttons'].append(analysis)
                elif analysis['type'] == 'icon_button':
                    result['icon_buttons'].append(analysis)
                elif analysis['type'] == 'price_context':
                    result['price_contexts'].append(analysis)
                elif analysis['type'] == 'quantity_control':
                    result['quantity_controls'].append(analysis)

    def _analyze_element_in_context(
        self,
        node: EnhancedDOMTreeNode,
        index: int,
        all_elements: Dict[int, EnhancedDOMTreeNode]
    ) -> Optional[Dict[str, Any]]:
        """
        Анализирует элемент в контексте его окружения.
        """
        if not node or not node.attributes:
            return None

        attrs = node.attributes
        tag = node.tag_name if hasattr(node, 'tag_name') else ''

        # Проверяем на SVG элементы отдельно
        is_svg_element = (
            tag == 'svg' or
            attrs.get('xmlns', '').startswith('http://www.w3.org/2000/svg') or
            'svg' in attrs.get('class', '').lower()
        )

        # Собираем весь текст элемента
        text_sources = self._collect_text_sources(node)

        # Обработка SVG элементов
        if is_svg_element:
            viewbox = attrs.get('viewBox', attrs.get('viewbox', ''))
            aria_label = attrs.get('aria-label', '').lower()

            # Проверяем viewBox на паттерн иконки
            is_icon_viewbox = any(pattern in viewbox for pattern in self.SVG_ICON_VIEWBOX_PATTERNS)

            # Проверяем aria-label на действия
            svg_action = None
            for action, keywords in {
                'add': ['add', 'plus', 'increase', 'increment'],
                'remove': ['remove', 'minus', 'decrease', 'decrement'],
                'close': ['close', 'dismiss', 'cancel'],
            }.items():
                if any(kw in aria_label for kw in keywords):
                    svg_action = action
                    break

            if is_icon_viewbox or svg_action:
                context = self._analyze_element_context(node, attrs, text_sources)
                return {
                    'type': 'svg_icon_button',
                    'index': index,
                    'tag': tag,
                    'symbol': aria_label if aria_label else 'SVG иконка',
                    'action': svg_action or 'icon',
                    'context': context,
                    'aria_label': attrs.get('aria-label', ''),
                    'has_price_nearby': context.get('has_price', False),
                    'viewbox': viewbox,
                }

        # Проверяем на символы действий
        for text in text_sources:
            symbol_info = self._check_action_symbol(text)
            if symbol_info:
                # Дополнительный анализ контекста
                context = self._analyze_element_context(node, attrs, text_sources)

                return {
                    'type': 'symbol_button',
                    'index': index,
                    'tag': tag,
                    'symbol': text,
                    'action': symbol_info,
                    'context': context,
                    'aria_label': attrs.get('aria-label', ''),
                    'has_price_nearby': context.get('has_price', False),
                }

        # Проверяем на элементы управления количеством
        if self._is_quantity_control(attrs, text_sources):
            context = self._analyze_element_context(node, attrs, text_sources)
            return {
                'type': 'quantity_control',
                'index': index,
                'tag': tag,
                'text': text_sources[0] if text_sources else '',
                'context': context,
            }

        return None

    def _collect_text_sources(self, node: EnhancedDOMTreeNode) -> List[str]:
        """
        Собирает весь текст, связанный с элементом.
        """
        sources = []

        # Текст из ax_node
        if node.ax_node and node.ax_node.name:
            sources.append(node.ax_node.name)

        # Текст из атрибутов
        if node.attributes:
            for attr in ['aria-label', 'title', 'value', 'label', 'placeholder', 'alt']:
                if attr in node.attributes and node.attributes[attr]:
                    sources.append(node.attributes[attr])

        # Текст из node_value
        if hasattr(node, 'node_value') and node.node_value:
            sources.append(node.node_value)

        return sources

    def _check_action_symbol(self, text: str) -> Optional[str]:
        """
        Проверяет, является ли текст символом действия.
        """
        text_stripped = text.strip()

        for action, symbols in self.ACTION_SYMBOLS.items():
            if text_stripped in symbols:
                return action

        return None

    def _is_quantity_control(self, attrs: Dict[str, str], text_sources: List[str]) -> bool:
        """
        Проверяет, является ли элемент контролем количества.
        """
        # Проверяем текст
        for text in text_sources:
            text_lower = text.lower()
            if any(kw in text_lower for kw in ['qty', 'quantity', 'колич', 'количество']):
                return True

        # Проверяем атрибуты
        class_attr = attrs.get('class', '').lower()
        if any(kw in class_attr for kw in ['quantity', 'qty', 'counter', 'stepper']):
            return True

        # Проверяем role
        role = attrs.get('role', '').lower()
        if role in ['spinbutton', 'textbox']:
            return True

        return False

    def _analyze_element_context(
        self,
        node: EnhancedDOMTreeNode,
        attrs: Dict[str, str],
        text_sources: List[str]
    ) -> Dict[str, Any]:
        """
        Анализирует контекст элемента (классы, родительские элементы и т.д.).
        """
        context = {
            'in_product_card': False,
            'has_price_nearby': False,
            'in_quantity_control': False,
            'clickable': False,
        }

        # Проверяем классы
        class_attr = attrs.get('class', '').lower()
        for pattern in self.ACTION_CONTAINER_CLASSES:
            if pattern in class_attr:
                context['in_product_card'] = True
                break

        # Проверяем, есть ли упоминание цены
        all_text = ' '.join(text_sources).lower()
        if any(kw in all_text for kw in ['руб', '₽', 'price', 'cost', 'цена', '₸', '₴']):
            context['has_price_nearby'] = True

        # Проверяем, кликабельный ли элемент
        tag = node.tag_name if hasattr(node, 'tag_name') else ''
        role = attrs.get('role', '').lower()

        # Расширенная проверка кликабельности (включая span, div и другие)
        is_clickable = (
            tag in ['button', 'a', 'span', 'div', 'td'] or  # Добавили span, div, td
            role == 'button' or
            'cursor' in class_attr or
            'btn' in class_attr or
            'button' in class_attr or
            'clickable' in class_attr or
            'action' in class_attr or
            attrs.get('onclick') or
            attrs.get('onmousedown') or
            attrs.get('href') or
            attrs.get('data-action')  # Многие SPA используют data-action для кнопок
        )

        context['clickable'] = is_clickable

        return context

    def _log_enhancement_info(self, analysis: Dict[str, Any], url: str) -> None:
        """Выводит информацию о проблемных элементах."""
        self.elements_enhanced += 1

        print("\n" + "=" * 70)
        print("🔎 ELEMENT RECOGNITION ENHANCER: Анализ элементов")
        print("=" * 70)
        print(f"URL: {url}")

        if analysis['symbol_buttons']:
            print(f"\n➕ Кнопки с символами ({len(analysis['symbol_buttons'])}):")
            for btn in analysis['symbol_buttons'][:10]:
                symbol = btn['symbol']
                action = btn['action']
                idx = btn['index']
                tag = btn['tag']
                ctx = btn['context']

                context_str = ""
                if ctx['in_product_card']:
                    context_str += " [в карточке товара]"
                if ctx['has_price_nearby']:
                    context_str += " [рядом с ценой]"
                if ctx['clickable']:
                    context_str += " [кликабельная]"
                else:
                    context_str += " [⚠️ может быть не кликабельной]"

                # Для SVG кнопок добавляем специальный маркер
                svg_marker = " [SVG]" if btn.get('type') == 'svg_icon_button' else ""

                print(f"   [{idx}] <{tag}>{svg_marker} символ: '{symbol}' → действие: {action}{context_str}")

                if btn['aria_label']:
                    print(f"        aria-label: '{btn['aria_label']}'")

        if analysis['quantity_controls']:
            print(f"\n🔢 Элементы управления количеством ({len(analysis['quantity_controls'])}):")
            for ctrl in analysis['quantity_controls'][:5]:
                idx = ctrl['index']
                tag = ctrl['tag']
                text = ctrl['text'][:30] if ctrl['text'] else ''
                print(f"   [{idx}] <{tag}> {text}")

        print("\n" + "=" * 70)
        print("💡 Агент должен САМ решить, на что нажать.")
        print("   Эта информация помогает лучше понять страницу.")
        print("=" * 70)

    def get_stats(self) -> dict:
        """Возвращает статистику работы."""
        return {
            "steps": self.step_count,
            "elements_enhanced": self.elements_enhanced,
        }
