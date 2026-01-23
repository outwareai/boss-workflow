# Boss Workflow - Code Style and Conventions

## Code Style
- **Language:** Python 3.10+
- **Async/Await:** Use async/await for all I/O operations
- **Type Hints:** Required on all function signatures
- **Docstrings:** Required for public functions
- **Logging:** Use structlog logger, never print()
- **Error Handling:** Handle exceptions gracefully, log errors, don't crash the bot

## Naming Conventions
- **Files:** snake_case (e.g., `task_processor.py`)
- **Classes:** PascalCase (e.g., `TaskRepository`)
- **Functions:** snake_case (e.g., `get_task_by_id`)
- **Constants:** UPPER_SNAKE_CASE (e.g., `SHEET_DAILY_TASKS`)
- **Private:** Prefix with underscore (e.g., `_internal_method`)

## File Organization
```
src/
├── main.py                 # FastAPI entry point
├── bot/
│   ├── handler.py         # Unified message handler
│   └── commands.py        # Slash commands
├── ai/
│   ├── deepseek.py        # AI integration
│   ├── intent.py          # Intent detection
│   ├── clarifier.py       # Smart question generation
│   └── task_processor.py  # Task generation
├── database/
│   ├── models.py          # SQLAlchemy models
│   ├── connection.py      # DB connection
│   ├── sync.py            # Sheets ↔ DB sync
│   └── repositories/      # CRUD operations
├── integrations/
│   ├── sheets.py          # Google Sheets
│   ├── discord.py         # Discord webhooks
│   ├── calendar.py        # Google Calendar
│   └── gmail.py           # Gmail integration
├── scheduler/
│   └── jobs.py            # Scheduled tasks
├── models/
│   └── task.py            # Task model (14 statuses)
└── memory/
    └── preferences.py     # User preferences

config/
└── settings.py            # Environment configuration
```

## Google Sheets Names (EXACT)
- `📋 Daily Tasks`
- `📊 Dashboard`
- `👥 Team`
- `📅 Weekly Reports`
- `📆 Monthly Reports`
- `📝 Notes Log`
- `🗃️ Archive`
- `⚙️ Settings`

## Task Statuses (14 Total)
pending, in_progress, in_review, awaiting_validation, needs_revision, completed, cancelled, blocked, delayed, undone, on_hold, waiting, needs_info, overdue

## Best Practices
- Read `FEATURES.md` FIRST before making changes
- Update `FEATURES.md` LAST after implementing features
- Test locally before deploying: `python -m src.main`
- Use `test_full_loop.py` for integration testing
- Never duplicate existing features
- Keep emoji prefixes exact in sheet names
- Avoid over-engineering: only make requested changes
- Don't add features, refactors, or "improvements" beyond what was asked
