# CI/CD Pipeline Documentation

This document describes the complete CI/CD pipeline for Boss Workflow, including setup, configuration, and troubleshooting.

## Overview

The CI/CD pipeline consists of three main workflows:

```
┌─────────────────────────────────────────────────────────────┐
│                      CI/CD PIPELINE                          │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  1. CI PIPELINE (ci.yml)                                    │
│     ├── Lint (flake8 + black)                               │
│     ├── Test (pytest on 3.10, 3.11, 3.12)                  │
│     ├── Smoke Tests                                         │
│     ├── Security Scan (bandit)                              │
│     └── Build Status Check                                  │
│                                                              │
│  2. DEPLOY PIPELINE (deploy.yml)                            │
│     ├── Deploy to Railway (master branch only)              │
│     ├── Wait for deployment                                 │
│     ├── Verify deployment                                   │
│     └── Deployment summary                                  │
│                                                              │
│  3. PR AUTO-COMMENT (pr-comment.yml)                        │
│     ├── Run tests                                           │
│     ├── Generate coverage report                            │
│     └── Post results as PR comment                          │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## Pipeline Details

### 1. CI Pipeline (`ci.yml`)

**Triggers:**
- Push to `master`, `main`, or `develop` branches
- Pull requests to `master` or `main`

**Jobs:**

#### 1.1 Lint
- Runs `flake8` with max line length 120
- Runs `black` to check code formatting
- Ignores common false positives (E203, E501, W503)

#### 1.2 Test
- Matrix testing on Python 3.10, 3.11, 3.12
- Runs all unit tests with pytest
- Generates coverage report
- Uploads coverage to Codecov (Python 3.11 only)
- Uses pip cache to speed up runs

#### 1.3 Smoke Tests
- Runs critical smoke tests
- Validates core functionality before deployment

#### 1.4 Security
- Runs Bandit security scanner
- Checks for common security issues in Python code
- Uploads security report as artifact

#### 1.5 Build Status
- Aggregates results from all jobs
- Blocks merge if tests fail
- Creates step summary with results

**Success Criteria:**
- All lint checks pass
- All tests pass on all Python versions
- Smoke tests pass
- Security scan completes (warnings allowed)

### 2. Deploy Pipeline (`deploy.yml`)

**Triggers:**
- Push to `master` branch
- Manual workflow dispatch

**Jobs:**

#### 2.1 Deploy
- Installs Railway CLI
- Links to `boss-workflow` project
- Deploys with `railway up --detach`
- Waits 60 seconds for deployment
- Runs deployment verification (optional)
- Creates deployment summary

**Required Secrets:**
- `RAILWAY_TOKEN` - Railway API token
- `TELEGRAM_BOT_TOKEN` - For E2E verification
- `TELEGRAM_BOSS_CHAT_ID` - For E2E verification

**Success Criteria:**
- Railway deployment succeeds
- Deployment verification passes (optional)

### 3. PR Auto-Comment (`pr-comment.yml`)

**Triggers:**
- Pull request opened
- Pull request synchronized (new commits)

**Jobs:**

#### 3.1 Comment
- Runs unit tests
- Generates coverage report
- Extracts test summary
- Posts formatted comment on PR

**Output Example:**
```markdown
## Test Results

✅ **Passed:** 470
❌ **Failed:** 0
⏭️ **Skipped:** 5

### Details
[Last 50 lines of test output]

### Coverage Report
[Coverage table with percentages]
```

## Setup Instructions

### Step 1: Configure GitHub Secrets

Use the automated script:

```bash
chmod +x scripts/setup_github_secrets.sh
./scripts/setup_github_secrets.sh
```

Or manually add secrets in GitHub:
1. Go to **Settings** → **Secrets and variables** → **Actions**
2. Add the following secrets:

| Secret | Description | Required For |
|--------|-------------|--------------|
| `RAILWAY_TOKEN` | Railway API token | Deploy workflow |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token | E2E tests |
| `TELEGRAM_BOSS_CHAT_ID` | Boss chat ID | E2E tests |
| `DEEPSEEK_API_KEY` | DeepSeek API key | Integration tests |
| `CODECOV_TOKEN` | Codecov token | Coverage (optional) |

### Step 2: Setup Branch Protection

Follow instructions in `.github/BRANCH_PROTECTION.md`:

1. Go to **Settings** → **Branches** → **Add rule**
2. Branch name pattern: `master`
3. Enable:
   - ✅ Require status checks to pass before merging
   - ✅ Require branches to be up to date before merging
   - Required checks: `lint`, `test`, `smoke-tests`, `build-status`
   - ✅ Require pull request reviews before merging (1 review)
   - ✅ Require conversation resolution before merging
   - ✅ Require linear history

### Step 3: Setup Codecov (Optional)

1. Go to https://codecov.io/
2. Sign in with GitHub
3. Enable coverage for `outwareai/boss-workflow`
4. Copy the Codecov token
5. Add as `CODECOV_TOKEN` secret in GitHub

### Step 4: Verify Setup

1. Create a test branch:
   ```bash
   git checkout -b test-ci-pipeline
   ```

2. Make a small change and commit:
   ```bash
   echo "# Test CI" >> README.md
   git add README.md
   git commit -m "test: Verify CI pipeline"
   git push -u origin test-ci-pipeline
   ```

3. Open a pull request

4. Verify:
   - CI pipeline runs automatically
   - All checks appear in the PR
   - Test results commented on PR
   - Merge button is disabled until checks pass

## Workflow Triggers

### What Triggers Each Workflow?

| Workflow | Push to master | Push to develop | PR to master | Manual |
|----------|----------------|-----------------|--------------|--------|
| CI Pipeline | ✅ | ✅ | ✅ | ❌ |
| Deploy | ✅ | ❌ | ❌ | ✅ |
| PR Comment | ❌ | ❌ | ✅ | ❌ |
| Test Suite | ✅ | ❌ | ✅ | ✅ |
| Smoke Tests | ✅ | ✅ | ✅ | ✅ |

### Typical Development Flow

```
1. Create feature branch
   ↓
2. Make changes and commit
   ↓
3. Push to GitHub
   ↓
4. Open PR to master
   ↓
5. CI Pipeline runs automatically
   ├── Lint
   ├── Test (3.10, 3.11, 3.12)
   ├── Smoke Tests
   └── Security Scan
   ↓
6. PR Auto-Comment posts test results
   ↓
7. Request review from teammate
   ↓
8. Address feedback if needed
   ↓
9. Merge PR (only if all checks pass)
   ↓
10. Deploy workflow triggers automatically
    ├── Deploy to Railway
    ├── Wait 60 seconds
    └── Verify deployment
    ↓
11. Production is updated!
```

## Troubleshooting

### CI Pipeline Failures

#### Lint Failures
```
Error: flake8 found issues
```

**Solution:**
```bash
# Fix automatically with black
black src tests --line-length=120

# Check what will be formatted
black --check src tests --line-length=120

# Fix flake8 issues manually
flake8 src tests --max-line-length=120
```

#### Test Failures
```
Error: pytest failed
```

**Solution:**
```bash
# Run tests locally
pytest tests/unit/ -v

# Run with coverage to see what's missing
pytest tests/unit/ -v --cov=src

# Run specific failing test
pytest tests/unit/test_command_handler.py::test_help_command -v
```

#### Smoke Test Failures
```
Error: Critical smoke tests failed
```

**Solution:**
```bash
# Run smoke tests locally
pytest tests/smoke/test_critical_intents.py -v

# Check if test file exists
ls tests/smoke/

# Create test file if missing
mkdir -p tests/smoke
touch tests/smoke/test_critical_intents.py
```

### Deployment Failures

#### Railway Token Invalid
```
Error: Railway authentication failed
```

**Solution:**
1. Generate new token at https://railway.app/account/tokens
2. Update `RAILWAY_TOKEN` secret in GitHub
3. Retry deployment

#### Deployment Verification Failed
```
Error: verify-deploy failed
```

**Solution:**
- This is non-critical (continues with warning)
- Check Railway logs: `railway logs -s boss-workflow`
- Verify manually by testing the bot

### PR Comment Not Appearing

**Possible Causes:**
1. No PR permissions for GitHub token
2. Test output too large
3. Workflow file has errors

**Solution:**
```bash
# Check workflow runs
gh run list --workflow=pr-comment.yml

# View specific run logs
gh run view <run-id> --log

# Test locally
pytest tests/unit/ -v --tb=short > test-output.txt
cat test-output.txt
```

## Monitoring and Maintenance

### View Pipeline Status

```bash
# List recent workflow runs
gh run list --limit 10

# View specific workflow runs
gh run list --workflow=ci.yml

# View detailed run
gh run view <run-id>

# Download artifacts
gh run download <run-id>
```

### Performance Optimization

Current pipeline timings:
- **Lint:** ~30 seconds
- **Test:** ~2-3 minutes (per Python version)
- **Smoke Tests:** ~1 minute
- **Security:** ~30 seconds
- **Total CI time:** ~6-8 minutes

Optimization tips:
1. Use pip cache (already implemented)
2. Run jobs in parallel (already implemented)
3. Skip optional steps on draft PRs
4. Use matrix strategy for testing (already implemented)

### Cost Estimates

GitHub Actions free tier:
- **Public repos:** Unlimited minutes
- **Private repos:** 2,000 minutes/month

Typical monthly usage:
- 30 PRs × 8 min = 240 minutes
- 30 master pushes × 10 min = 300 minutes
- **Total:** ~540 minutes/month (well within free tier)

## Advanced Configuration

### Skip CI on Certain Commits

Add to commit message:
```bash
git commit -m "docs: Update README [skip ci]"
```

### Run Deployment Manually

```bash
# Via GitHub CLI
gh workflow run deploy.yml

# Via GitHub UI
Actions → Deploy to Railway → Run workflow
```

### Add Additional Status Checks

Edit `.github/workflows/ci.yml`:

```yaml
  custom-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run custom check
        run: |
          # Your custom check here
          echo "Running custom validation"
```

Then update branch protection to require `custom-check`.

## Best Practices

1. **Always run tests locally before pushing**
   ```bash
   pytest tests/unit/ -v
   ```

2. **Keep commits small and focused**
   - Easier to review
   - Faster to debug failures
   - Clearer history

3. **Write descriptive commit messages**
   ```bash
   # Good
   git commit -m "fix(auth): Handle expired tokens in OAuth flow"

   # Bad
   git commit -m "fix stuff"
   ```

4. **Monitor CI failures**
   - Fix immediately
   - Don't let failures accumulate
   - Investigate flaky tests

5. **Keep dependencies updated**
   - Review Dependabot PRs weekly
   - Test thoroughly after updates
   - Check for breaking changes

## References

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Railway Documentation](https://docs.railway.app/)
- [Codecov Documentation](https://docs.codecov.com/)
- [Branch Protection Rules](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/defining-the-mergeability-of-pull-requests/about-protected-branches)
