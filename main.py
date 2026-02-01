#!/usr/bin/env python3
"""
Browser Agent — простой CLI для выполнения задач через браузер с Polza.ai LLM.

Использование:
    python main.py "зайди на яндекс еду и закажи пиццу"
    python main.py "найди статью про python на wikipedia"
"""

import asyncio
import os
import sys
import io
from pathlib import Path

# Устанавливаем UTF-8 кодировку для консоли Windows
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

from dotenv import load_dotenv

from browser_use.agent.service import Agent
from browser_use.browser.session import BrowserSession
from browser_use.browser.profile import BrowserProfile
from browser_use.llm.openai.chat import ChatOpenAI

load_dotenv()


def get_polza_llm(model: str = "openai/gpt-4o", temperature: float = 0.0):
    """
    Создаёт LLM клиент для Polza.ai (OpenAI-совместимый API).

    Args:
        model: Название модели (например: openai/gpt-4o, deepcogito/cogito-v2.1-671b)
        temperature: Температура для генерации
    """
    api_key = os.getenv("POLZA_API_KEY") or os.getenv("OPENAI_API_KEY")

    if not api_key:
        print("Ошибка: POLZA_API_KEY или OPENAI_API_KEY не найден в .env")
        print("Создай файл .env с ключом:")
        print("POLZA_API_KEY=твой_ключ")
        sys.exit(1)

    return ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url="https://api.polza.ai/v1",  # Polza.ai API endpoint
        temperature=temperature,
    )


async def run_task(task: str, model: str = "openai/gpt-4o", headless: bool = False):
    """
    Выполняет задачу в браузере.

    Args:
        task: Описание задачи на русском или английском
        model: Название модели для Polza.ai
        headless: Запускать браузер в фоновом режиме (без UI)
    """
    print(f"Запускаю агента с задачей: {task}")
    print(f"Модель: {model}")
    print(f"Режим браузера: {'фоновой' if headless else 'видимый'}")
    print("-" * 50)

    # Создаём LLM клиент
    llm = get_polza_llm(model=model)

    # Создаём браузерную сессию
    browser_profile = BrowserProfile(
        headless=headless,
        # Можно добавить user_data_dir для сохранения сессий
        # user_data_dir=str(Path.home() / ".browser-agent" / "profile"),
    )

    browser_session = BrowserSession(browser_profile=browser_profile)

    try:
        # Создаём и запускаем агента
        agent = Agent(
            task=task,
            llm=llm,
            browser_session=browser_session,
        )

        await agent.run()

        print("-" * 50)
        print("Задача выполнена!")

    except KeyboardInterrupt:
        print("\nПрервано пользователем")
    except Exception as e:
        print(f"\nОшибка: {e}")
        raise
    finally:
        # Закрываем браузер
        await browser_session.stop()


def main():
    """Точка входа для CLI."""
    if len(sys.argv) < 2:
        print("Browser Agent — AI агент для браузера")
        print("")
        print("Использование:")
        print("  python main.py \"твоя задача\"")
        print("")
        print("Примеры:")
        print("  python main.py \"зайди на яндекс еду и закажи пиццу пепперони\"")
        print("  python main.py \"найди статью про Python на Википедии\"")
        print("  python main.py \"открой GitHub и найди репозиторий browser-use\"")
        print("")
        print("Переменные окружения (.env):")
        print("  POLZA_API_KEY=твой_ключ")
        print("  OPENAI_API_KEY=твой_ключ  # альтернатива")
        print("")
        print("Опции:")
        print("  --model MODEL    Модель LLM (default: openai/gpt-4o)")
        print("  --headless       Фоновый режим браузера")
        sys.exit(1)

    # Парсим аргументы
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
            # Всё что не флаг — это задача
            task = arg
            i += 1

    if not task:
        print("Не указана задача")
        sys.exit(1)

    # Запускаем
    asyncio.run(run_task(task, model=model, headless=headless))


if __name__ == "__main__":
    main()
