# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Проект

Browser Agent — тестовое задание для автоматизации браузера через LLM (Polza.ai/OpenAI). Пользователь отправляет текстовую задачу, агент выполняет её в видимом браузере автономно.

## Критические требования

**ЗАПРЕЩЕНО:**
- Жёсткие инструкции/подсказки в промпте — агент должен сам догадываться о кнопках, ссылках, селекторах
- Заготовки действий для конкретных задач (шаги заказа пиццы и т.п.)
- Хардкод селекторов (например `a[data-qa='vacancy']`)
- Подсказки по ссылкам и элементам (нельзя хардкодить что /vacancies — это страница вакансий)

**ОБЯЗАТЕЛЬНО:**
- Минималистичный системный промпт (только общие принципы, никаких детальных инструкций)
- Хотя бы один продвинутый паттерн: multi-agent architecture, sub-agent, error handling, или security layer
- Модель с vision-поддержкой (browser-use отправляет скриншоты страницы)

## Запуск

```bash
# Базовый запуск
python main.py "текст задачи"

# С другой моделью
python main.py --model anthropic/claude-sonnet-4 "текст задачи"

# Фоновый режим
python main.py --headless "текст задачи"

# Режим отладки
python main.py --debug "текст задачи"
```

## Multi-Agent Architecture

Проект использует настоящую multi-agent архитектуру с тремя специализированными агентами:

### Компоненты

**MultiAgentCoordinator** (`agent_system/coordinator.py`) — центральный координатор:
- Создаёт и управляет всеми агентами
- Интегрируется с browser-use Agent через callback
- Патчит AgentMessagePrompt для инъекции ContextHints в промпт
- Патчит лимит информации о странице (150K вместо 40K)

**Perception Agent** (`agents/perception_agent.py`) — анализ страницы:
- Определяет тип страницы (catalog, product, cart, checkout, etc.)
- Обнаруживает паттерны (модальные окна, пагинация, формы, quantity controls)
- Категоризирует интерактивные элементы
- NO хардкод селекторов — только эвристики
- Добавляет наблюдения в ContextHints (НЕ инструкции, только факты о странице)

**Reflection Agent** (`agents/reflection_agent.py`) — оценка прогресса:
- Оценивает успешность выполненных действий
- Подсчитывает прогресс (0.0 - 1.0)
- Анализирует ошибки
- Предлагает корректировки

**Shared Memory** (`agent_system/shared_memory.py`) — общая память:
- Thread-safe хранилище для всех агентов
- Ключи: TASK_DESCRIPTION, CURRENT_URL, PERCEPTION_RESULT, REFLECTION_RESULT, PROGRESS_SCORE, CONTEXT_HINTS

**EventBus** (`agent_system/agent_message.py`) — система сообщений:
- Асинхронная передача сообщений между агентами
- Типы: PERCEPTION_PAGE_ANALYZED, REFLECTION_PROGRESS_UPDATED, ACTION_COMPLETED, etc.

**Sequential Thinking Engine** (`agent_system/sequential_thinking.py`) — пошаговое мышление:
- Цепочка: thought -> observation -> action -> reflection
- Отслеживание прогресса

### Context Injection — КРИТИЧЕСКИЙ ПАТЧ

В `agent_system/coordinator.py` есть патч `_patched_get_user_message` который инъектирует ContextHints в промпт browser-use Agent.

**ВАЖНО:** Патч должен модифицировать UserMessage объект, а не возвращать строку!

```python
# ПРАВИЛЬНО — модифицируем объект:
if hasattr(original, 'content'):
    if isinstance(original.content, str):
        original.content = f"{original.content}\n\n{context_str}"
    elif isinstance(original.content, list):
        for item in original.content:
            if hasattr(item, 'text'):
                item.text = f"{item.text}\n\n{context_str}"
                break
return original

# НЕПРАВИЛЬНО — возвращает строку (вызывает ошибку 'str' object has no attribute 'text'):
# return f"{original}\n\n{context_str}"
```

## Поток выполнения

```
1. Пользователь запускает задачу
   └─> python main.py "зайди на яндекс еду"

2. Создаётся MultiAgentCoordinator
   └─> Инициализируются все агенты и компоненты

3. Запускается browser-use Agent с register_new_step_callback
   └─> Агент browser-use выполняет действия в браузере

4. После каждого шага вызывается _step_callback:
   ├─> BrowserAdapter обновляет состояние (async!)
   ├─> Perception Agent анализирует страницу
   ├─> Reflection Agent оценивает прогресс
   └─> ContextHints сохраняются для инъекции в следующий промпт

5. Цикл продолжается до:
   ├─> Задача выполнена (done action)
   ├─> Достигнут max_steps
   └─> Пользователь прервал выполнение
```

## Установка зависимостей

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

## Модели

**По умолчанию:** `openai/gpt-4o` (поддерживает vision)

**Доступные на Polza.ai:**
- `openai/gpt-4o`
- `openai/gpt-4o-mini`
- `anthropic/claude-sonnet-4`

## Persistent sessions

Браузер сохраняет сессию в `~/.browser-agent/profile/`. Пользователь может войти в аккаунт вручную, агент продолжит работу.

## Структура проекта

```
browseragent/
├── agent_system/              # Инфраструктура multi-agent системы
│   ├── __init__.py
│   ├── agent_base.py          # Базовый класс Agent
│   ├── agent_message.py       # EventBus, MessageType
│   ├── shared_memory.py       # SharedMemory, MemoryKey, ContextHints
│   ├── browser_adapter.py     # BrowserAdapter, BrowserState
│   ├── sequential_thinking.py # SequentialThinkingEngine
│   └── coordinator.py         # MultiAgentCoordinator, патчи
├── agents/                    # Специализированные агенты
│   ├── __init__.py
│   ├── perception_agent.py    # Perception Agent
│   └── reflection_agent.py    # Reflection Agent
├── main.py                    # Точка входа
├── requirements.txt           # Зависимости
└── MULTI_AGENT_ARCHITECTURE.md # Документация архитектуры
```

## Важные ограничения при разработке

**Из requements.md — Чего не должно быть:**

1. **НЕ добавляйте жёсткие инструкции в промпт** — агент должен сам догадываться
2. **НЕ хардкодьте селекторы** — используйте эвристики
3. **НЕ создавайте заготовки действий** — агент должен решать автономно
4. **НЕ давайте подсказки по ссылкам и элементам** — агент должен сам определить что нажать
5. **Держите системный промпт минималистичным** — только общие принципы
6. **При патче get_user_message** — модифицируйте UserMessage объект, не возвращайте строку

**Правило для ContextHints:**
- Добавляйте **наблюдения** (факты о странице), а не инструкции
- Пример ПРАВИЛЬНО: "На странице есть элементы управления количеством (+/- кнопки)"
- Пример НЕПРАВИЛЬНО: "Не нажимай на кнопку Увеличить если пользователь просит 1 товар"

Агент сам принимает решения на основе наблюдений и задачи пользователя.

## Примеры задач из requements.md

```bash
# Оформить заказ на сервисе доставки еды
python main.py "закажи мне BBQ-бургер и картошку фри из [ресторан]"

# Добавить товар в корзину
python main.py "положи пиццу в корзину"

# Добавить несколько товаров
python main.py "положи две пиццы в корзину"
```

Важно: агент должен сам разобраться:
- Найти ресторан/товар
- Различать похожие товары
- Работать с quantity controls (если пользователь просит 2 товара — нажать + один раз)
