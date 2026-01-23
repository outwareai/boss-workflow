&nbsp;# Boss Workflow - Master Prompt



&nbsp; ## Project Context

&nbsp; This is the Boss Workflow project - a Telegram bot that creates tasks via AI and posts to Discord/Sheets.

&nbsp; - Repo: github.com/outwareai/boss-workflow

&nbsp; - Deployed on: Railway (service: boss-workflow)

&nbsp; - Stack: Python, FastAPI, DeepSeek AI, PostgreSQL, Redis



&nbsp; ## Mandatory Files to Read

&nbsp; - `FEATURES.md` - READ FIRST, UPDATE LAST

&nbsp; - `CLAUDE.md` - Workflow rules and project structure

&nbsp; - `PLAN\_V2.2.md` - Current implementation reference



&nbsp; ## Sequential Workflow (ALWAYS FOLLOW)



&nbsp; For any significant task:



&nbsp; 1. `/brainstorm "task description"`

&nbsp;    → Generate 2-3 approaches

&nbsp;    → Recommend BEST (not simplest)

&nbsp;    → ASK user which approach



&nbsp; 2. `/write-plan`

&nbsp;    → Create detailed implementation plan

&nbsp;    → Identify files to change



&nbsp; 3. `/ralph-loop "Execute the plan with test\_full\_loop.py validation"`

&nbsp;    → Implement changes

&nbsp;    → Deploy: `railway redeploy -s boss-workflow --yes`

&nbsp;    → Test: `python test\_full\_loop.py full-test "message"`

&nbsp;    → Read logs: `railway logs -s boss-workflow | tail -40`

&nbsp;    → Iterate until working

&nbsp;    → Use `<promise>DONE</promise>` when complete



&nbsp; 4. `/code-review`

&nbsp;    → Review all changes made



&nbsp; 5. `/commit` or `/commit-push-pr`

&nbsp;    → Commit with conventional format



&nbsp; ## Test Framework Commands

&nbsp; ```bash

&nbsp; python test\_full\_loop.py send "message"       # Send to bot

&nbsp; python test\_full\_loop.py respond "yes"        # Answer confirmation

&nbsp; python test\_full\_loop.py read-tasks           # Check database

&nbsp; python test\_full\_loop.py read-discord         # Check Discord output

&nbsp; python test\_full\_loop.py full-test "message"  # Complete test cycle

&nbsp; railway logs -s boss-workflow | tail -40      # Check processing logs



&nbsp; Available Plugins (Use Them!)

&nbsp; ┌───────────────────┬──────────────────────────────────────────────┐

&nbsp; │      Plugin       │                 When to Use                  │

&nbsp; ├───────────────────┼──────────────────────────────────────────────┤

&nbsp; │ /brainstorm       │ Before any feature work                      │

&nbsp; ├───────────────────┼──────────────────────────────────────────────┤

&nbsp; │ /write-plan       │ After choosing approach                      │

&nbsp; ├───────────────────┼──────────────────────────────────────────────┤

&nbsp; │ /ralph-loop       │ For iterative implementation                 │

&nbsp; ├───────────────────┼──────────────────────────────────────────────┤

&nbsp; │ /code-review      │ After implementation                         │

&nbsp; ├───────────────────┼──────────────────────────────────────────────┤

&nbsp; │ /commit           │ To commit changes                            │

&nbsp; ├───────────────────┼──────────────────────────────────────────────┤

&nbsp; │ /feature-dev      │ For new features (3-agent workflow)          │

&nbsp; ├───────────────────┼──────────────────────────────────────────────┤

&nbsp; │ context7          │ Auto-fetches docs when you mention libraries │

&nbsp; ├───────────────────┼──────────────────────────────────────────────┤

&nbsp; │ pyright-lsp       │ Python type checking (always on)             │

&nbsp; ├───────────────────┼──────────────────────────────────────────────┤

&nbsp; │ security-guidance │ Vulnerability detection (always on)          │

&nbsp; └───────────────────┴──────────────────────────────────────────────┘

&nbsp; Key Rules



&nbsp; 1. NEVER implement without asking which approach first

&nbsp; 2. ALWAYS test with real data via test\_full\_loop.py

&nbsp; 3. NEVER say "done" without showing test results

&nbsp; 4. ALWAYS give end-of-workflow summary with: what was implemented, what was tested, commits, status



&nbsp; Team Members (for testing)



&nbsp; - Mayank = Developer → routes to DEV channel

&nbsp; - Zea = Admin → routes to ADMIN channel



&nbsp; ---

&nbsp; TASK: \[DESCRIBE YOUR TASK HERE]

