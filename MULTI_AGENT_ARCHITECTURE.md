# Multi-Agent Architecture

## Обзор

Проект Browser Agent теперь использует настоящую multi-agent архитектуру с тремя специализированными агентами и sequential thinking engine.

## Архитектура

```
┌─────────────────────────────────────────────────────────────┐
│                    MultiAgentCoordinator                     │
│  (управляет всеми агентами и координирует их взаимодействие)  │
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

## Компоненты

### 1. Perception Agent (`agents/perception_agent.py`)

**Ответственность:**
- Анализ текущего состояния страницы
- Определение типа страницы (catalog, product, cart, checkout, etc.)
- Обнаружение паттернов (модальные окна, пагинация, формы)
- Категоризация интерактивных элементов

**Ключевые особенности:**
- NO хардкод селекторов
- Использует эвристики и контекст
- Минималистичный системный промпт

### 2. Reflection Agent (`agents/reflection_agent.py`)

**Ответственность:**
- Оценка успешности выполненных действий
- Подсчёт прогресса выполнения задачи (0.0 - 1.0)
- Анализ ошибок
- Принятие решения о продолжении/корректировке

**Ключевые особенности:**
- Автономное принятие решений
- Генерация следующих шагов
- Предложение корректировок при ошибках

### 3. Sequential Thinking Engine (`agent_system/sequential_thinking.py`)

**Ответственность:**
- Пошаговое мышление
- Цепочка мыслей: thought -> observation -> action -> reflection
- Отслеживание прогресса

**Структура ThoughtStep:**
```python
@dataclass
class ThoughtStep:
    step_number: int
    thought: str        # Что агент думает
    observation: str    # Что агент наблюдает
    action: str         # Что агент собирается делать
    reflection: str     # Оценка предыдущего действия
    next_thought: str   # Что будет дальше
```

### 4. Shared Memory (`agent_system/shared_memory.py`)

**Ответственность:**
- Общее хранилище для всех агентов
- Thread-safe доступ
- Подписка на изменения

**Ключевые данные:**
- `TASK_DESCRIPTION` - описание задачи
- `CURRENT_URL` - текущий URL
- `PERCEPTION_RESULT` - результат восприятия
- `REFLECTION_RESULT` - результат рефлексии
- `PROGRESS_SCORE` - прогресс выполнения (0.0 - 1.0)
- `THOUGHT_CHAIN` - цепочка мыслей

### 5. EventBus (`agent_system/agent_message.py`)

**Ответственность:**
- Асинхронная передача сообщений между агентами
- Подписка на типы сообщений
- История сообщений

**Типы сообщений:**
- `PERCEPTION_PAGE_ANALYZED` - страница проанализирована
- `PERCEPTION_PATTERN_DETECTED` - паттерн обнаружен
- `REFLECTION_ACTION_EVALUATED` - действие оценено
- `REFLECTION_PROGRESS_UPDATED` - прогресс обновлён
- `ACTION_COMPLETED` - действие выполнено
- `ACTION_FAILED` - действие не удалось

### 6. BrowserAdapter (`agent_system/browser_adapter.py`)

**Ответственность:**
- Адаптация между нашими агентами и browser-use
- Хранение состояния браузера
- Обновление через callback от browser-use

### 7. MultiAgentCoordinator (`agent_system/coordinator.py`)

**Ответственность:**
- Создание и управление всеми агентами
- Интеграция с browser-use Agent
- Callback обработка
- Статистика выполнения

## Поток выполнения

```
1. Пользователь запускает задачу
   └─> python main.py "зайди на яндекс еду"

2. Создаётся MultiAgentCoordinator
   └─> Инициализируются все агенты и компоненты

3. Запускается browser-use Agent с callback
   └─> Агент browser-use выполняет действия в браузере

4. После каждого шага вызывается callback:
   ├─> BrowserAdapter обновляет состояние
   ├─> Perception Agent анализирует страницу
   ├─> Reflection Agent оценивает прогресс
   └─> Результаты сохраняются в Shared Memory

5. Цикл продолжается до:
   ├─> Задача выполнена (progress >= 1.0)
   ├─> Достигнут max_steps
   └─> Пользователь прервал выполнение

6. Результат возвращается пользователю
```

## Критические требования

✅ **ВЫПОЛНЕНО:**
- NO хардкод селекторов - агенты используют эвристики
- NO жёстких инструкций - минималистичные промпты
- Vision поддержка - через browser-use
- Совместимость с browser-use сохранена

## Использование

```bash
# Базовый запуск
python main.py "зайди на яндекс еду"

# С другой моделью
python main.py --model anthropic/claude-sonnet-4 "зайди на самокат"

# Фоновый режим
python main.py --headless "найди статью про Python"

# Режим отладки
python main.py --debug "зайди на самокат"
```

## Структура проекта

```
browseragent/
├── agent_system/              # Инфраструктура multi-agent системы
│   ├── __init__.py
│   ├── agent_base.py          # Базовый класс Agent
│   ├── agent_message.py       # Система сообщений (EventBus)
│   ├── shared_memory.py       # Общая память
│   ├── browser_adapter.py     # Адаптер для browser-use
│   ├── sequential_thinking.py # Движок sequential thinking
│   └── coordinator.py         # MultiAgentCoordinator
├── agents/                    # Специализированные агенты
│   ├── __init__.py
│   ├── perception_agent.py    # Perception Agent (ПРИОРИТЕТ)
│   ├── reflection_agent.py    # Reflection Agent (ПРИОРИТЕТ)
│   └── action_agent.py        # Action Agent (резерв)
├── main.py                    # Точка входа
└── ...
```

## Следующие шаги

### Возможные улучшения:

1. **Action Agent** - полное внедрение для прямого выполнения действий
2. **Более глубокая интеграция с browser-use** - извлечение элементов для Perception Agent
3. **Planning Agent** - отдельный агент для планирования
4. **Memory System** - долгосрочная память между сессиями
5. **Learning from experience** - обучение на прошлых выполнениях

### Тестирование:

```bash
# Базовая навигация
python main.py "зайди на яндекс еду"

# Поиск информации
python main.py "найди статью про Python на Википедии"

# Покупки (без оплаты)
python main.py "зайди на самокат и добавь сэндвич в корзину"
```

## Статус реализации

| Компонент | Статус | Приоритет |
|-----------|--------|-----------|
| AgentBase | ✅ | Базовый |
| EventBus | ✅ | Базовый |
| SharedMemory | ✅ | Базовый |
| BrowserAdapter | ✅ | Базовый |
| SequentialThinking | ✅ | Базовый |
| MultiAgentCoordinator | ✅ | Базовый |
| Perception Agent | ✅ | **ПРИОРИТЕТ #1** |
| Reflection Agent | ✅ | **ПРИОРИТЕТ #2** |
| Action Agent | ⚠️ Резерв | Низкий |

✅ - Полностью реализовано
⚠️ - Частично реализовано/резерв
