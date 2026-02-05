#!/usr/bin/env python3
"""
Browser Agent — AI агент для автоматизации браузера.

НОВАЯ МУЛЬТИ-АГЕНТНАЯ АРХИТЕКТУРА:
- Perception Agent: анализ страницы и паттернов
- Reflection Agent: оценка прогресса и принятие решений
- Sequential Thinking: пошаговое мышление
- browser-use Agent: выполнение действий в браузере

КРИТИЧЕСКИ ВАЖНЫЕ ПРАВИЛА:
- NO хардкод селекторов
- NO жёстких инструкций
- Минималистичные системные промпты

Использование:
    python main.py "зайди на яндекс еду и закажи пиццу"
"""

import asyncio
import io
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Устанавливаем UTF-8 кодировку для консоли Windows
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

from browser_use import ChatOpenAI

from agent_system.coordinator import create_coordinator, SYSTEM_PROMPT

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
# MAIN ENTRY POINT
# =============================================================================

async def run_task(task: str, model: str = "openai/gpt-4o", headless: bool = False, debug: bool = False):
    """Выполняет задачу с помощью multi-agent системы."""
    print(f"Запускаю агента с задачей: {task}")
    print(f"Модель: {model}")
    print(f"Режим браузера: {'видимый'}")
    print("-" * 50)
    print("🧠 Multi-Agent Architecture:")
    print("   👁️  Perception Agent - анализ страницы и паттернов")
    print("   🤔 Reflection Agent - оценка прогресса и принятие решений")
    print("   🔗 Sequential Thinking - пошаговое мышление")
    print("   🤖 browser-use Agent - выполнение действий")
    print("-" * 50)

    llm = get_polza_llm(model=model)

    try:
        # Create coordinator with all agents
        coordinator = await create_coordinator(
            llm=llm,
            headless=headless,
            max_steps=25,
            debug=debug,
        )

        # Run the task
        result = await coordinator.run_with_agents(task)

        print("-" * 50)
        print("✅ Задача выполнена!")
        print(f"Результат: {result}")

        # Print stats
        stats = coordinator.get_stats()
        print(f"\n📊 Статистика:")
        print(f"  Шагов выполнено: {stats['steps']}")
        print(f"  Прогресс: {stats['progress']*100:.0f}%")

        return result

    except KeyboardInterrupt:
        print("\n❌ Прервано пользователем")
    except Exception as e:
        print(f"\n⚠️  Ошибка: {e}")
        raise
    finally:
        # Keep browser open for user
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
            # Browser is kept alive, user can close it manually
            print("✅ Выход выполнен")


def main():
    """Точка входа для CLI."""
    if len(sys.argv) < 2:
        print("Browser Agent — AI агент для браузера")
        print("")
        print("🧠 Multi-Agent Architecture:")
        print("  - Perception Agent: анализ страницы и паттернов")
        print("  - Reflection Agent: оценка прогресса и принятие решений")
        print("  - Sequential Thinking: пошаговое мышление")
        print("  - browser-use Agent: выполнение действий")
        print("")
        print("КРИТИЧЕСКИЕ ПРИНЦИПЫ:")
        print("  - NO хардкод селекторов")
        print("  - NO жёстких инструкций")
        print("  - Минималистичные промпты")
        print("  - Автономное выполнение")
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
        print("  --debug          Режим отладки (verbose output)")
        sys.exit(1)

    task = None
    model = "openai/gpt-4o"
    headless = False
    debug = False

    i = 1
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg == "--model" and i + 1 < len(sys.argv):
            model = sys.argv[i + 1]
            i += 2
        elif arg == "--headless":
            headless = True
            i += 1
        elif arg == "--debug":
            debug = True
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

    asyncio.run(run_task(task, model=model, headless=headless, debug=debug))


if __name__ == "__main__":
    main()
