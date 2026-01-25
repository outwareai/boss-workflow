# CI/CD Quick Reference

Quick commands and references for the CI/CD pipeline.

## Status Badges

Current status: Check the README badges

- [![CI Pipeline](https://github.com/outwareai/boss-workflow/workflows/CI%20Pipeline/badge.svg)](https://github.com/outwareai/boss-workflow/actions/workflows/ci.yml)
- [![Test Suite](https://github.com/outwareai/boss-workflow/workflows/Test%20Suite/badge.svg)](https://github.com/outwareai/boss-workflow/actions/workflows/test.yml)
- [![Deploy](https://github.com/outwareai/boss-workflow/workflows/Deploy%20to%20Railway/badge.svg)](https://github.com/outwareai/boss-workflow/actions/workflows/deploy.yml)

## Quick Commands

### Local Testing

```bash
# Run all unit tests
pytest tests/unit/ -v

# Run tests with coverage
pytest tests/unit/ -v --cov=src --cov-report=html

# Run smoke tests
pytest tests/smoke/ -v

# Lint code
flake8 src tests --max-line-length=120
black --check src tests --line-length=120

# Fix formatting
black src tests --line-length=120

# Security scan
bandit -r src
```

### GitHub Actions

```bash
# List recent runs
gh run list --limit 10

# View CI pipeline runs
gh run list --workflow=ci.yml

# View deployment runs
gh run list --workflow=deploy.yml

# View specific run
gh run view <run-id> --log

# Trigger manual deployment
gh workflow run deploy.yml

# Download artifacts
gh run download <run-id>
```

### Railway

```bash
# View logs
railway logs -s boss-workflow

# Deploy manually
railway up --detach -s boss-workflow

# Check status
railway status -s boss-workflow

# View variables
railway variables -s boss-workflow

# Set variable
railway variables set -s boss-workflow "VAR_NAME=value"
```

### Git Workflow

```bash
# Create feature branch
git checkout -b feature/my-feature

# Make changes and commit
git add .
git commit -m "feat: Add new feature"

# Push and create PR
git push -u origin feature/my-feature
gh pr create --title "Feature: My Feature" --body "Description"

# Check PR status
gh pr status

# Merge PR (after approval)
gh pr merge --squash
```

## Troubleshooting

### Tests Failing

```bash
# Run specific test
pytest tests/unit/test_command_handler.py -v

# Run with more output
pytest tests/unit/ -v --tb=long

# Run last failed tests
pytest --lf
```

### Deployment Issues

```bash
# Check Railway deployment
railway logs -s boss-workflow --tail

# Verify deployment
python test_full_loop.py verify-deploy

# Check Railway status
railway status -s boss-workflow
```

### CI Pipeline Blocked

```bash
# Check what's failing
gh run list --workflow=ci.yml --limit 1
gh run view --log

# Common fixes:
black src tests --line-length=120  # Fix formatting
pytest tests/unit/ -v              # Run tests locally
```

## Required Secrets

| Secret | Get From | Used By |
|--------|----------|---------|
| `RAILWAY_TOKEN` | railway.app/account/tokens | deploy.yml |
| `TELEGRAM_BOT_TOKEN` | @BotFather | test.yml, deploy.yml |
| `TELEGRAM_BOSS_CHAT_ID` | Telegram | test.yml, deploy.yml |
| `DEEPSEEK_API_KEY` | platform.deepseek.com | test.yml |
| `CODECOV_TOKEN` | codecov.io | ci.yml (optional) |

## Branch Protection

**Required checks for master:**
- lint
- test
- smoke-tests
- build-status

**Settings:**
- ✅ Require status checks before merging
- ✅ Require branch up to date
- ✅ Require 1 review
- ✅ Require conversation resolution
- ✅ Require linear history

## Coverage Targets

| Coverage | Status |
|----------|--------|
| 70%+ | ✅ Excellent |
| 60-70% | ⚠️ Good |
| 50-60% | ⚠️ Acceptable |
| <50% | ❌ Need improvement |

**Current:** ~65%

## Performance Targets

| Metric | Target | Current |
|--------|--------|---------|
| CI Pipeline | <10 min | ~8 min |
| Lint | <1 min | ~30 sec |
| Tests | <5 min | ~3 min |
| Deploy | <3 min | ~2 min |

## Common Scenarios

### Scenario 1: New Feature

```bash
git checkout -b feature/task-templates
# Make changes
pytest tests/unit/ -v
black src tests --line-length=120
git add .
git commit -m "feat: Add task templates"
git push -u origin feature/task-templates
gh pr create
# Wait for CI to pass
# Get review approval
gh pr merge --squash
```

### Scenario 2: Fix Bug

```bash
git checkout -b fix/validation-error
# Fix bug
pytest tests/unit/test_validation_handler.py -v
git add .
git commit -m "fix(validation): Handle None values correctly"
git push -u origin fix/validation-error
gh pr create
```

### Scenario 3: Emergency Deploy

```bash
# Fix issue locally
git add .
git commit -m "hotfix: Fix critical auth issue"
git push origin master
# Wait for auto-deploy
railway logs -s boss-workflow --tail
```

### Scenario 4: Rollback

```bash
# Find last good commit
git log --oneline

# Revert to it
git revert <commit-hash>
git push origin master
# Auto-deploys reverted version
```

## Links

- [Full CI/CD Documentation](../docs/CICD_SETUP.md)
- [Branch Protection Setup](.github/BRANCH_PROTECTION.md)
- [GitHub Actions](https://github.com/outwareai/boss-workflow/actions)
- [Railway Dashboard](https://railway.app/project/boss-workflow)
- [Codecov](https://codecov.io/gh/outwareai/boss-workflow)
