# Boss Workflow - Suggested Commands

## Running the Application
```bash
# Start locally
python -m src.main

# Or with uvicorn
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

## Testing
```bash
# Run all tests
python test_all.py

# Run specific test suites
python test_intents.py
python test_conversations.py
python test_task_ops.py
python test_telegram_discord.py
python test_advanced.py

# Full integration testing
python test_full_loop.py send "message"
python test_full_loop.py test-simple
python test_full_loop.py test-complex
python test_full_loop.py test-all
python test_full_loop.py verify-deploy
```

## Database Setup
```bash
# Initialize Google Sheets structure
python setup_sheets.py

# Clear mock data
python clear_mock_data.py

# Migrate attendance data
python migrate_attendance.py
```

## Railway Deployment
```bash
# View variables
railway variables -s boss-workflow

# Set a variable
railway variables set -s boss-workflow "VAR_NAME=value"

# Redeploy
railway redeploy -s boss-workflow --yes

# View logs
railway logs -s boss-workflow

# Check status
railway status -s boss-workflow
```

## Git Commands (Windows MINGW64)
```bash
git add .
git commit -m "feat: description"
git push origin master

# Railway auto-deploys on push to master
```

## System Utils (Windows MINGW64)
- `ls` - List files
- `cd` - Change directory
- `grep -r "pattern" src/` - Search code
- `find src/ -name "*.py"` - Find files
- `cat file.txt` - Read file
- `tail -f logs/app.log` - Follow logs
