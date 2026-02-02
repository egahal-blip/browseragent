#!/usr/bin/env python3
"""
Browser Agent — AI агент для автоматизации браузера.

КРИТИЧЕСКИ ВАЖНЫЕ ПРАВИЛА БЕЗОПАСНОСТИ:
- НИКОГДА не оплачивать без подтверждения пользователя
- ВСЕГДА проверять модальные окна
- ОСТАНАВЛИВАТЬСЯ перед финальным действием

Использование:
    python main.py "зайди на яндекс еду и закажи пиццу"
"""

import asyncio
import os
import sys
import io
import re
from pathlib import Path

# Устанавливаем UTF-8 кодировку для консоли Windows
if sys.platform == "win32":
	sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
	sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

from dotenv import load_dotenv

from browser_use import Agent, BrowserSession, BrowserProfile, ChatOpenAI
from browser_use.agent.prompts import AgentMessagePrompt
from browser_use.browser.views import BrowserStateSummary
from browser_use.agent.views import AgentOutput

from security_layer import SecurityLayer, SecurityLayerBlockedAction
from modal_enhancer import ModalEnhancer
from button_hint_helper import ButtonHintHelper
from element_recognition_enhancer import ElementRecognitionEnhancer


load_dotenv()


def get_polza_llm(model: str = "openai/gpt-4o", temperature: float = 0.0):
	"""Создаёт LLM клиент для Polza.ai (OpenAI-совместимый API)."""
	api_key = os.getenv("POLZA_API_KEY") or os.getenv("OPENAI_API_KEY")

	if not api_key:
		print("Ошибка: POLZA_API_KEY или OPENAI_API_KEY не найден в .env")
		print("Создай файл .env с ключом:")
		print("POLZA_API_KEY=твой_ключ")
		sys.exit(1)

	return ChatOpenAI(
		model=model,
		api_key=api_key,
		base_url="https://api.polza.ai/v1",
		temperature=temperature,
	)


# =============================================================================
# ПАТЧ ДЛЯ УВЕЛИЧЕНИЯ ЛИМИТА ИНФОРМАЦИИ О СТРАНИЦЕ
# =============================================================================

_original_agent_message_prompt_init = AgentMessagePrompt.__init__

def _patched_agent_message_prompt_init(self, *args, **kwargs):
	"""Патченый __init__ с увеличенным лимитом информации о странице."""
	if 'max_clickable_elements_length' not in kwargs:
		kwargs['max_clickable_elements_length'] = 150000  # 150K вместо 40K
	_original_agent_message_prompt_init(self, *args, **kwargs)

AgentMessagePrompt.__init__ = _patched_agent_message_prompt_init


# =============================================================================
# СИСТЕМНЫЙ ПРОМПТ С БЕЗОПАСНОСТЬЮ
# =============================================================================

SECURITY_PROMPT = """

Ты — автономный AI-агент для работы с браузером.

ПРАВИЛА:
- Выполняй задачу пользователя autonomously
- Останавливайся когда задача выполнена
- Не совершай финальную оплату без подтверждения
- Работай в одной вкладке
- Отвечай на русском языке
"""


# =============================================================================
# SUB-AGENT COORDINATOR
# =============================================================================

class SubAgentCoordinator:
	"""Координатор с интегрированным Security Layer, Modal Enhancer, Button Hint Helper и Element Recognition Enhancer."""

	def __init__(self, browser_session: BrowserSession, llm: ChatOpenAI):
		self.browser_session = browser_session
		self.llm = llm
		self.security_layer = SecurityLayer()
		self.modal_enhancer = ModalEnhancer(debug=True)
		self.button_hint_helper = ButtonHintHelper(debug=True)
		self.element_recognition_enhancer = ElementRecognitionEnhancer(debug=True)

	async def _combined_step_callback(
		self,
		browser_state: 'BrowserStateSummary',
		agent_output: 'AgentOutput',
		step: int
	) -> None:
		"""Комбинированный callback, который вызывает security_layer, modal_enhancer, button_hint_helper и element_recognition_enhancer."""
		# Сначала вызываем modal_enhancer для детекции модальных окон
		await self.modal_enhancer(browser_state, agent_output, step)

		# Вызываем button_hint_helper для анализа кнопок
		await self.button_hint_helper(browser_state, agent_output, step)

		# Вызываем element_recognition_enhancer для улучшения распознавания элементов
		await self.element_recognition_enhancer(browser_state, agent_output, step)

		# Затем вызываем security_layer для проверки безопасности
		# (он может вызвать исключение для блокировки опасных действий)
		await self.security_layer(browser_state, agent_output, step)

	async def run_with_sub_agent(self, task: str) -> str:
		"""Запускает выполнение задачи с Security Layer, Modal Enhancer и Button Hint Helper."""
		print("\n🤖 Запуск агента с Security Layer, Modal Enhancer и Button Hint Helper")

		agent = Agent(
			task=task,
			llm=self.llm,
			browser_session=self.browser_session,
			extend_system_message=SECURITY_PROMPT,
			max_steps=25,  # Ограничиваем количество шагов чтобы агент не блуждал бесконечно
			include_attributes=[
				# Базовые атрибуты
				'aria-label', 'title', 'placeholder', 'name', 'type',
				'value', 'href', 'id', 'class',
				# Для тестирования
				'data-testid', 'data-qa', 'data-cy',
				# Для модальных окон и опций
				'role', 'aria-modal', 'aria-selected', 'aria-checked',
				'checked', 'selected', 'disabled', 'readonly',
				# Для текстового контента
				'text-content', 'alt', 'label',
				# Дополнительные атрибуты для модальных окон
				'style', 'tabindex', 'data-dismiss', 'data-toggle',
				# Для кнопок и интерактивных элементов
				'onclick', 'onmousedown', 'data-action', 'data-type',
				'aria-disabled', 'data-role', 'data-goal',
			],
			# ИНТЕГРИРУЕМ КОМБИНИРОВАННЫЙ CALLBACK
			register_new_step_callback=self._combined_step_callback,
		)

		history = await agent.run()

		# Выводим статистику Security Layer, Modal Enhancer, Button Hint Helper и Element Recognition Enhancer
		stats = self.security_layer.get_stats()
		modal_stats = self.modal_enhancer.get_stats()
		button_stats = self.button_hint_helper.get_stats()
		element_stats = self.element_recognition_enhancer.get_stats()
		print("\n" + "=" * 50)
		print(f"📊 Статистика работы:")
		print(f"  Всего шагов: {stats['steps']}")
		print(f"  Security Layer:")
		print(f"    Разрешено: {stats['allowed']}")
		print(f"    Заблокировано: {stats['blocked']}")
		print(f"  Modal Enhancer:")
		print(f"    Модальных окон обнаружено: {modal_stats['modals_detected']}")
		print(f"  Button Hint Helper:")
		print(f"    Подсказок выдано: {button_stats['hints_given']}")
		print(f"  Element Recognition Enhancer:")
		print(f"    Элементов проанализировано: {element_stats['elements_enhanced']}")
		print("=" * 50)

		if history and len(history) > 0:
			result = history[-1].result
			if isinstance(result, dict) and 'text' in result:
				return result['text']
			elif hasattr(result, 'text'):
				return result.text
			elif isinstance(result, str):
				return result

		return 'Задача выполнена'


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

async def run_task(task: str, model: str = "openai/gpt-4o", headless: bool = False):
	"""Выполняет задачу с Security Layer, Modal Enhancer, Button Hint Helper и Element Recognition Enhancer."""
	print(f"Запускаю агента с задачей: {task}")
	print(f"Модель: {model}")
	print(f"Режим браузера: {'видимый'}")
	print("-" * 50)
	print("🔐 Security Layer: активен")
	print("   ✓ Checkout разрешён (до финальной оплаты)")
	print("   ✗ Финальная оплата ЗАПРЕЩЕНА")
	print("   ✗ Новые вкладки ЗАПРЕЩЕНЫ")
	print("👁️  Modal Enhancer: активен")
	print("   ✓ Детекция модальных окон (role, aria-modal)")
	print("   ✓ Приоритетизация элементов модального окна")
	print("   ✓ Подсказки для действий в модальном окне")
	print("🔍 Button Hint Helper: активен")
	print("   ✓ Умный поиск кнопок (без хардкода)")
	print("   ✓ Контекстные подсказки агенту")
	print("   ✓ Эвристики для корзины/оформления")
	print("🔎 Element Recognition Enhancer: активен")
	print("   ✓ Распознавание кнопок-символов (+, -, и т.д.)")
	print("   ✓ Анализ контекста элементов")
	print("   ✓ Выявление некликабельных элементов")
	print("-" * 50)

	llm = get_polza_llm(model=model)

	browser_profile = BrowserProfile(
		headless=headless,
		user_data_dir=str(Path.home() / ".browser-agent" / "profile"),
		keep_alive=True,  # Браузер остаётся открытым после завершения агента
	)

	browser_session = BrowserSession(browser_profile=browser_profile)
	coordinator = SubAgentCoordinator(browser_session, llm)

	try:
		result = await coordinator.run_with_sub_agent(task)
		print("-" * 50)
		print("✅ Задача выполнена!")
		print(f"Результат: {result}")

	except KeyboardInterrupt:
		print("\n❌ Прервано пользователем")
	except SecurityLayerBlockedAction as e:
		print(f"\n🔒 {e}")
		print("Агент остановился из-за попытки опасного действия.")
	except Exception as e:
		print(f"\n⚠️  Ошибка: {e}")
		raise
	finally:
		# Браузер остаётся открытым благодаря keep_alive=True
		print("\n" + "=" * 60)
		print("🔵 БРАУЗЕР ОСТАЁТСЯ ОТКРЫТЫМ")
		print("=" * 60)
		print("Вы можете:")
		print("  - Продолжить работу в браузере вручную")
		print("  - Нажать Ctrl+C чтобы закрыть браузер и выйти")
		print("=" * 60)

		try:
			await asyncio.Event().wait()
		except KeyboardInterrupt:
			print("\n🛑 Закрытие браузера по запросу пользователя...")
			await browser_session.stop()
			print("✅ Браузер закрыт")


def main():
	"""Точка входа для CLI."""
	if len(sys.argv) < 2:
		print("Browser Agent — AI агент для браузера С БЕЗОПАСНОСТЬЮ")
		print("")
		print("🔐 Security Layer:")
		print("  - Разрешает: добавление в корзину, checkout, заполнение данных")
		print("  - Блокирует: финальную оплату (Pay Now, Confirm Payment)")
		print("  - Блокирует: открытие новых вкладок")
		print("👁️  Modal Enhancer:")
		print("  - Детектирует модальные окна")
		print("  - Приоритизирует элементы модальных окон")
		print("🔍 Button Hint Helper:")
		print("  - Умный поиск кнопок (БЕЗ хардкода селекторов)")
		print("  - Контекстные подсказки для агента")
		print("🔎 Element Recognition Enhancer:")
		print("  - Распознаёт кнопки-символы (+, -, и т.д.)")
		print("  - Анализирует контекст элементов")
		print("")
		print("Использование:")
		print("  python main.py \"твоя задача\"")
		print("")
		print("Примеры:")
		print("  python main.py \"зайди на самокат и найди сэндвич\"")
		print("  python main.py \"найди пиццу на яндекс еде и добавь в корзину\"")
		print("  python main.py \"оформи сэндвич с курицей\"")
		print("")
		print("Опции:")
		print("  --model MODEL    Модель LLM (default: openai/gpt-4o)")
		print("  --headless       Фоновый режим браузера")
		sys.exit(1)

	task = None
	model = "openai/gpt-4o"
	headless = False

	i = 1
	while i < len(sys.argv):
		arg = sys.argv[i]
		if arg == "--model" and i + 1 < len(sys.argv):
			model = sys.argv[i + 1]
			i += 2
		elif arg == "--headless":
			headless = True
			i += 1
		elif arg.startswith("--"):
			print(f"Неизвестная опция: {arg}")
			sys.exit(1)
		else:
			task = arg
			i += 1

	if not task:
		print("Не указана задача")
		sys.exit(1)

	asyncio.run(run_task(task, model=model, headless=headless))


if __name__ == "__main__":
	main()
