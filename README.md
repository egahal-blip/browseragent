# Browser Agent

AI агент для автоматизации браузера через LLM с **Multi-Agent Architecture**.

## Что это такое

AI агент, который принимает текстовые задачи от пользователя и выполняет их в видимом браузере автономно.

**Пример:**
```bash
python main.py "закажи мне BBQ-бургер и картошку фри"
```

## Технологии

### browser-use
Основная библиотека для автоматизации браузера через LLM. Отвечает за:
- Управление браузером (Playwright)
- Получение скриншотов и DOM-снимков страницы
- Интерпретацию действий LLM в команды браузера
- Интеграцию с vision-моделями

**Репозиторий:** [browser-use/browser-use](https://github.com/browser-use/browser-use)

## Multi-Agent Architecture

Проект использует настоящую multi-agent архитектуру с тремя специализированными агентами:

```
┌─────────────────────────────────────────────────────────────┐
│                    MultiAgentCoordinator                     │
│              (управляет всеми агентами)                       │
└─────────────────────────────────────────────────────────────┘
                          │
        ┌─────────────────┼─────────────────┐
        │                 │                 │
        ▼                 ▼                 ▼
   ┌─────────┐      ┌─────────┐      ┌─────────┐
   │Percept. │      │Reflect. │      │Browser  │
   │ Agent   │◄────►│ Agent   │      │Agent    │
   └─────────┘      └─────────┘      │(browser- │
        │                 │             │use)     │
        └─────────────────┼─────────────┴─────────┘
                          │
                  ┌───────┴───────┐
                  ▼               ▼
            ┌─────────┐     ┌─────────┐
            │  Shared │     │  Event  │
            │ Memory  │◄────┤   Bus   │
            └─────────┘     └─────────┘
```

### Компоненты

**Perception Agent** — анализ страницы:
- Определяет тип страницы (catalog, product, cart, checkout)
- Обнаруживает паттерны (модальные окна, пагинация, формы, quantity controls)
- Категоризирует интерактивные элементы
- NO хардкод селекторов — только эвристики
- Добавляет наблюдения в ContextHints (НЕ инструкции!)

**Reflection Agent** — оценка прогресса:
- Оценивает успешность выполненных действий
- Подсчитывает прогресс (0.0 - 1.0)
- Анализирует ошибки и предлагает корректировки

**Sequential Thinking Engine** — пошаговое мышление:
- Цепочка: thought → observation → action → reflection
- Отслеживание прогресса выполнения задачи

**Shared Memory** — общая память для всех агентов:
- Thread-safe хранилище
- Ключи: TASK_DESCRIPTION, CURRENT_URL, PERCEPTION_RESULT, REFLECTION_RESULT, PROGRESS_SCORE, CONTEXT_HINTS

**EventBus** — система сообщений:
- Асинхронная передача сообщений между агентами
- Типы: PERCEPTION_PAGE_ANALYZED, REFLECTION_PROGRESS_UPDATED, ACTION_COMPLETED

**Context Injection** — инъекция контекста в промпт:
- Агенты передают ContextHints в browser-use Agent
- Патчит AgentMessagePrompt.get_user_message
- Модифицирует UserMessage объект (не возвращает строку!)

## Установка

```bash
cd browseragent

# Создай виртуальное окружение (опционально)
python -m venv .venv
.venv\Scripts\activate  # Windows

# Установи зависимости
pip install -r requirements.txt
python -m playwright install chromium
```

## Конфигурация

Создай файл `.env`:
```
POLZA_API_KEY=твой_ключ_от_polza_ai
```

## Использование

### Базовый пример

```bash
python main.py "зайди на яндекс еду"
```

### С опциями

```bash
# Видимый браузер (по умолчанию)
python main.py "найди статью про Python на Википедии"

# Фоновый режим
python main.py --headless "открой GitHub и найди browser-use"

# Другая модель
python main.py --model anthropic/claude-sonnet-4 "закажи такси"

# Режим отладки
python main.py --debug "зайди на самокат"
```

### Примеры задач

```bash
# Навигация
python main.py "зайди на яндекс еду"

# Поиск информации
python main.py "найди курс доллара на Центробанке"

# Покупки (без оплаты)
python main.py "зайди на wildberries и найди кроссовки Nike"

# Оформление заказа (сложная задача)
python main.py "закажи мне BBQ-бургер и картошку фри"

# Добавление товара
python main.py "положи пиццу в корзину"

# Добавление нескольких товаров
python main.py "положи две пиццы в корзину"
```

## Доступные модели (Polza.ai)

- `openai/gpt-4o` — по умолчанию, поддерживает vision
- `openai/gpt-4o-mini` — дешевле и быстрее
- `anthropic/claude-sonnet-4` — Claude Sonnet 4

## Поток выполнения

```
1. Пользователь запускает задачу
   └─> python main.py "зайди на яндекс еду"

2. Создаётся MultiAgentCoordinator
   └─> Инициализируются все агенты

3. Запускается browser-use Agent с register_new_step_callback
   └─> Агент выполняет действия в браузере

4. После каждого шага вызывается callback:
   ├─> BrowserAdapter обновляет состояние
   ├─> Perception Agent анализирует страницу
   │   └─> Обнаруживает паттерны (quantity controls, модальные окна, etc.)
   │   └─> Добавляет наблюдения в ContextHints
   ├─> Reflection Agent оценивает прогресс
   └─> ContextHints инъектируются в следующий промпт

5. Цикл продолжается до выполнения задачи
```

## Persistent sessions

Браузер сохраняет сессию в `~/.browser-agent/profile/`. Пользователь может войти в аккаунт вручную, агент продолжит работу.

## Ограничения

**Чего НЕТ в реализации (соответствует требованиям):**
- NO жёстких инструкций — агент сам догадывается
- NO хардкод селекторов — только эвристики
- NO заготовок действий — агент решает автономно
- NO подсказок по элементам — только наблюдения

**Правило для ContextHints:**
- Добавляем **наблюдения** (факты о странице), а не инструкции
- ✅ ПРАВИЛЬНО: "На странице есть элементы управления количеством (+/- кнопки)"
- ❌ НЕПРАВИЛЬНО: "Не нажимай на кнопку Увеличить"

Агент сам принимает решения на основе наблюдений и задачи пользователя.

## Структура проекта

```
browseragent/
├── agent_system/              # Инфраструктура multi-agent системы
│   ├── coordinator.py         # MultiAgentCoordinator, патчи
│   ├── browser_adapter.py     # BrowserAdapter
│   ├── shared_memory.py       # SharedMemory, ContextHints
│   ├── agent_message.py       # EventBus, MessageType
│   ├── sequential_thinking.py # SequentialThinkingEngine
│   └── agent_base.py          # Базовый класс Agent
├── agents/                    # Специализированные агенты
│   ├── perception_agent.py    # Perception Agent
│   └── reflection_agent.py    # Reflection Agent
├── main.py                    # Точка входа
├── requirements.txt           # Зависимости
├── CLAUDE.md                  # Руководство для Claude Code
└── MULTI_AGENT_ARCHITECTURE.md # Документация архитектуры
```

## Troubleshooting

### Ошибка API ключа
```
❌ Ошибка: POLZA_API_KEY или OPENAI_API_KEY не найден в .env
```
Проверь что файл `.env` создан и ключ указан правильно

### Браузер не открывается
Установи Chromium:
```bash
python -m playwright install chromium
```
