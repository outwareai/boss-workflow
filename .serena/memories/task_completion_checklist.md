# Task Completion Checklist

## When a task is completed:

### 1. Testing
- [ ] Run locally: `python -m src.main`
- [ ] Test relevant features manually
- [ ] Run automated tests: `python test_all.py`
- [ ] Run integration tests if applicable: `python test_full_loop.py test-all`

### 2. Documentation
- [ ] Update `FEATURES.md` with new functionality
- [ ] Add inline code comments for complex logic
- [ ] Update docstrings if API changed

### 3. Code Quality
- [ ] No print() statements (use logger instead)
- [ ] Type hints on all new functions
- [ ] Proper error handling (try/except with logging)
- [ ] No hardcoded values (use config/env vars)

### 4. Git Commit
```bash
git add .
git commit -m "feat: description of changes"
git push origin master
```

### 5. Deployment
- [ ] Railway auto-deploys on push (wait ~2-3 minutes)
- [ ] Or manual: `railway redeploy -s boss-workflow --yes`
- [ ] Verify: `python test_full_loop.py verify-deploy`
- [ ] Check logs: `python test_full_loop.py check-logs`

### 6. Post-Deployment Testing
- [ ] Test in production environment (send test messages to bot)
- [ ] Check Railway logs for errors: `railway logs -s boss-workflow`
- [ ] Verify integrations (Discord, Sheets) are working

### 7. End-of-Task Summary
Provide clear summary:
- What was implemented (files modified)
- What was tested (test results)
- Commits made (hashes + messages)
- Status (complete/partial/blocked)
- Next steps (if any)

## No Linting/Formatting Tools
This project does not use automated linting or formatting tools (no black, flake8, pylint, etc.). Follow the code style conventions manually.
