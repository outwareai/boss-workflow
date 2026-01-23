# Boss Workflow Automation - Project Overview

## Purpose
A conversational task management system for bosses to manage their team via Telegram. It uses AI-powered natural language understanding to create tasks, track progress, and automate reporting.

## Tech Stack
- **Frontend:** Telegram Bot (python-telegram-bot 20.7)
- **AI:** DeepSeek AI (OpenAI-compatible API)
- **Backend:** FastAPI 0.109.0 + PostgreSQL + Redis
- **Integrations:** Discord.py 2.3.2, Google Sheets/Calendar/Gmail (gspread, Google APIs)
- **Deployment:** Railway with auto-scaling
- **Scheduler:** APScheduler 3.10.4
- **ORM:** SQLAlchemy 2.0.25 with asyncio support

## Key Dependencies
- fastapi, uvicorn - Web framework
- python-telegram-bot - Telegram integration
- discord.py, aiohttp - Discord integration
- gspread - Google Sheets
- openai - AI integration (DeepSeek compatible)
- asyncpg, sqlalchemy - Database
- redis, aioredis - Caching
- apscheduler - Job scheduling
- structlog - Logging

## Architecture
PostgreSQL → Source of Truth
Google Sheets → Boss Dashboard
Discord → Team Notifications
Redis → Caching/Sessions
Telegram → Input Interface
DeepSeek AI → Intent Detection + Task Generation
