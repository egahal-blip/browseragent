"""
Modal Enhancer — улучшает обработку модальных окон в браузер агенте.

Основные функции:
1. Детекция модальных окон на странице
2. Приоритизация элементов модальных окон в action map
3. Расширенное логирование для отладки
4. Логирование интерактивных элементов с индексами
"""

from typing import Optional, Any
from browser_use.browser.views import BrowserStateSummary
from browser_use.agent.views import AgentOutput
from browser_use.dom.views import SimplifiedNode


class ModalEnhancer:
    """
    Класс для улучшения работы агента с модальными окнами.

    Интегрируется через register_new_step_callback в browser-use.
    """

    def __init__(self, debug: bool = True):
        """
        Args:
            debug: Выводить отладочную информацию о модальных окнах
        """
        self.debug = debug
        self.step_count = 0
        self.modals_detected = 0

        # Признаки модальных окон в DOM
        self.modal_selectors = [
            'role="dialog"',
            'aria-modal="true"',
            'role="alertdialog"',
        ]

        # CSS классы, которые часто используются для модальных окон
        self.modal_class_patterns = [
            'modal',
            'dialog',
            'popup',
            'overlay',
            'backdrop',
            'lightbox',
            'drawer',
            'sidebar',
        ]

    async def __call__(
        self,
        browser_state: BrowserStateSummary,
        agent_output: AgentOutput,
        step: int
    ) -> None:
        """
        Callback функция для browser-use.

        Анализирует состояние страницы и логирует информацию о модальных окнах.
        """
        self.step_count += 1

        # Проверяем наличие модальных окон
        modal_info = self._detect_modals(browser_state)

        if modal_info['has_modal']:
            self.modals_detected += 1

            if self.debug:
                self._log_modal_detected(modal_info, browser_state)

            # Дополнительный анализ действий агента при открытом модальном окне
            self._analyze_agent_actions_for_modal(agent_output, modal_info)
        elif self.debug:
            print(f"  [ModalEnhancer] Шаг {step}: Модальных окон не обнаружено")

        # Логируем интерактивные элементы на странице
        if self.debug:
            self._log_interactive_elements(browser_state, step)

    def _detect_modals(self, browser_state: BrowserStateSummary) -> dict:
        """
        Детектирует наличие модальных окон на странице.

        Returns:
            dict с информацией о модальных окнах:
            - has_modal: bool - есть ли модальное окно
            - modal_elements: list - элементы модального окна
            - interactive_in_modal: int - количество интерактивных элементов в модальном окне
        """
        result = {
            'has_modal': False,
            'modal_elements': [],
            'interactive_in_modal': 0,
            'modal_types': [],
        }

        if not browser_state.dom_state or not browser_state.dom_state._root:
            return result

        def traverse_and_detect(node: SimplifiedNode, depth: int = 0) -> None:
            """Рекурсивно обходит DOM дерево в поисках модальных окон."""
            if not node or not node.original_node:
                return

            original = node.original_node

            # Проверяем атрибуты элемента
            if hasattr(original, 'attributes') and original.attributes:
                attrs = original.attributes

                # Проверяем role="dialog" или aria-modal="true"
                role = attrs.get('role', '').lower()
                aria_modal = attrs.get('aria-modal', '').lower()

                if role == 'dialog' or aria_modal == 'true' or role == 'alertdialog':
                    result['has_modal'] = True
                    result['modal_elements'].append({
                        'tag': original.tag_name,
                        'role': role,
                        'aria-modal': aria_modal,
                        'text': node.get_all_children_text()[:50] if hasattr(node, 'get_all_children_text') else '',
                    })
                    result['modal_types'].append(role if role else aria_modal)

                # Проверяем CSS классы
                class_attr = attrs.get('class', '').lower()
                for pattern in self.modal_class_patterns:
                    if pattern in class_attr:
                        # Дополнительная проверка - у модального окна обычно есть overlay
                        # или он фиксирован поверх других элементов
                        style = attrs.get('style', '').lower()
                        if 'position' in style or 'z-index' in style or 'fixed' in style:
                            result['has_modal'] = True
                            if class_attr not in result['modal_types']:
                                result['modal_types'].append(class_attr)
                            break

            # Считаем интерактивные элементы
            if hasattr(node, 'is_interactive') and node.is_interactive:
                result['interactive_in_modal'] += 1

            # Рекурсивно обходим детей
            for child in node.children:
                traverse_and_detect(child, depth + 1)

        traverse_and_detect(browser_state.dom_state._root)
        return result

    def _log_interactive_elements(self, browser_state: BrowserStateSummary, step: int) -> None:
        """
        Логирует интерактивные элементы с их индексами для отладки.

        Это помогает понять, какие элементы доступны для клика и какие индексы они имеют.
        """
        if not browser_state.dom_state or not browser_state.dom_state.selector_map:
            print(f"\n  [ModalEnhancer] Шаг {step}: Интерактивные элементы (с индексами):")
            print("  ⚠️ Интерактивные элементы не найдены!")
            return

        print(f"\n  [ModalEnhancer] Шаг {step}: Интерактивные элементы (с индексов: {len(browser_state.dom_state.selector_map)}):")

        # selector_map содержит dict[int, EnhancedDOMTreeNode]
        # где int - это индекс элемента для клика
        elements_found = []
        max_elements = 30  # Ограничиваем вывод

        for index, enhanced_node in browser_state.dom_state.selector_map.items():
            if len(elements_found) >= max_elements:
                break

            # Получаем текст элемента из различных источников
            text = ""
            try:
                # Пытаемся получить текст из ax_node
                if enhanced_node.ax_node and enhanced_node.ax_node.name:
                    text = enhanced_node.ax_node.name[:50]
                # Или из node_value
                elif enhanced_node.node_value:
                    text = enhanced_node.node_value[:50]
            except Exception:
                pass

            # Получаем основные атрибуты
            tag = enhanced_node.tag_name if hasattr(enhanced_node, 'tag_name') else ''
            attrs = enhanced_node.attributes if hasattr(enhanced_node, 'attributes') else {}

            # Определяем тип элемента
            element_type = tag
            role = attrs.get('role', '') if attrs else ''
            if role:
                element_type = f'{tag}[role="{role}"]'

            # Проверяем на классы, связанные с модальными окнами
            class_attr = attrs.get('class', '') if attrs else ''
            is_modal_related = any(p in class_attr.lower() for p in self.modal_class_patterns)

            # Проверяем aria-label (важно для кнопок)
            aria_label = attrs.get('aria-label', '') if attrs else ''

            elements_found.append({
                'index': index,
                'type': element_type,
                'text': text,
                'aria_label': aria_label[:30] if aria_label else '',
                'is_modal': is_modal_related,
                'class': class_attr[:30] if class_attr else '',
            })

        if elements_found:
            # Сортируем по индексу
            elements_found.sort(key=lambda x: x['index'])

            print("  Доступные для клика элементы:")
            for elem in elements_found[:20]:  # Первые 20 элементов
                modal_mark = " 🎯" if elem['is_modal'] else ""
                text_display = f"'{elem['text']}'" if elem['text'] else ''
                aria_display = f" aria-label:'{elem['aria_label']}'" if elem['aria_label'] else ''
                print(f"    [{elem['index']}] {elem['type']}: {text_display}{aria_display}{modal_mark}")
                if elem['class'] and elem['is_modal']:
                    print(f"         class: {elem['class']}")

            if len(browser_state.dom_state.selector_map) > max_elements:
                print(f"    ... (показано первые {max_elements} из {len(browser_state.dom_state.selector_map)} элементов)")
        else:
            print("  ⚠️ Интерактивные элементы не найдены!")

    def _log_modal_detected(self, modal_info: dict, browser_state: BrowserStateSummary) -> None:
        """Выводит детализированную информацию о обнаруженном модальном окне."""
        print("\n" + "=" * 60)
        print("🔔 MODAL ENHANCER: Обнаружено модальное окно!")
        print("=" * 60)
        print(f"URL: {browser_state.url}")
        print(f"Типы: {', '.join(set(modal_info['modal_types']))}")
        print(f"Интерактивных элементов на странице: {modal_info['interactive_in_modal']}")

        if modal_info['modal_elements']:
            print("\nЭлементы модального окна:")
            for elem in modal_info['modal_elements'][:5]:  # Первые 5 элементов
                print(f"  - <{elem['tag']}> role={elem['role']}: {elem['text'][:50]}")

        print("=" * 60)

    def _analyze_agent_actions_for_modal(self, agent_output: AgentOutput, modal_info: dict) -> None:
        """
        Анализирует планируемые действия агента и даёт рекомендации
        для работы с модальным окном.
        """
        actions = agent_output.action if agent_output.action else []

        if not actions:
            return

        if self.debug:
            print("\n💡 Рекомендации для модального окна:")
            print("   1. Работай ТОЛЬКО с элементами модального окна")
            print("   2. Если нужно выбрать опцию — выбери первую или помеченную как recommended")
            print("   3. После действия жди 1-2 секунды (add_action wait)")

            # Выводим планируемые действия
            print("\n   Планируемые действия агента:")
            for i, action in enumerate(actions[:5]):  # Первые 5 действий
                action_str = str(action)
                # Сокращаем длинные действия
                if len(action_str) > 100:
                    action_str = action_str[:97] + "..."
                print(f"     {i+1}. {action_str}")

            # Проверяем, есть ли wait в действиях
            has_wait = any('wait' in str(action).lower() for action in actions)
            if not has_wait:
                print("   ⚠️  ВНИМАНИЕ: Нет wait после действия в модальном окне!")

    def get_stats(self) -> dict:
        """Возвращает статистику работы."""
        return {
            "steps": self.step_count,
            "modals_detected": self.modals_detected,
        }
