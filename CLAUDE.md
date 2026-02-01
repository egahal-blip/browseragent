# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Проект

Browser Agent — тестовое задание для автоматизации браузера через LLM (Polza.ai/OpenAI). Пользователь отправляет текстовую задачу, агент выполняет её в видимом браузере автономно.

## Ключевые ограничения (из requements.md)

**ЗАПРЕЩЕНО:**
- Жёсткие инструкции/подсказки в промпте (агент должен сам догадываться о кнопках, ссылках, селекторах)
- Заготовки действий для конкретных задач (шаги заказа пиццы и т.п.)
- Хардкод селекторов (например `a[data-qa='vacancy']`)

**ОБЯЗАТЕЛЬНО:**
- Минималистичный системный промпт (только общие принципы)
- Хотя бы один продвинутый паттерн: sub-agent, error handling, или security layer
- Модель с vision-поддержкой (browser-use отправляет скриншоты страницы)

## Запуск

```bash
# Базовый запуск (видимый браузер)
python main.py "текст задачи"

# С другой моделью
python main.py --model anthropic/claude-sonnet-4 "текст задачи"

# Фоновый режим
python main.py --headless "текст задачи"
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

## Архитектура

```
main.py          — точка входа, создание Agent
security.py      — Security Layer (определение опасных действий)
error_handler.py — Error Handler (retry, fallback, логирование)
sub_agent.py     — Sub-Agent Pattern (координация операций)
```

**ВАЖНО:** Модули security.py, error_handler.py, sub_agent.py созданы, но пока НЕ интегрированы в main.py (требуется найти способ подключения через browser-use API).

## Persistent sessions

Браузер сохраняет сессию в `~/.browser-agent/profile/`. Пользователь может войти в аккаунт вручную, агент продолжит работу.

## Тестовые задачи

```bash
# Поиск информации
python main.py "найди статью про Python на Википедии"

# Покупки
python main.py "зайди на яндекс еду, найди пиццу и добавь в корзину"

# Соцсети
python main.py "открой YouTube и найди видео про browser automation"
```
