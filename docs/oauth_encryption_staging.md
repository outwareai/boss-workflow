# OAuth Encryption Staging Environment

## Overview

This document outlines the setup and testing procedures for the OAuth encryption staging environment. The staging environment allows safe testing of encryption changes before production deployment.

**Purpose:** Validate OAuth encryption without risking production data
**Duration:** Week 3 of OAuth encryption migration plan
**Completion criteria:** All tests pass, zero errors in staging logs

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     STAGING ENVIRONMENT                     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Railway Staging Service (boss-workflow-staging)           │
│  ├─ Copy of production code (encryption branch)            │
│  ├─ Separate PostgreSQL database                           │
│  ├─ Same ENCRYPTION_KEY as production                      │
│  └─ Test Telegram bot (@boss_workflow_staging_bot)         │
│                                                             │
│  Test Data:                                                 │
│  ├─ Copy of production OAuth tokens (anonymized)           │
│  ├─ Test Google accounts for Calendar/Tasks                │
│  └─ Dummy task data                                         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Setup Steps

### 1. Create Railway Staging Service

**Option A: Railway Dashboard (Recommended)**

1. Go to https://railway.app/dashboard
2. Click "New Project" → "Empty Project"
3. Name: `boss-workflow-staging`
4. Add PostgreSQL plugin:
   - Click "+ New" → "Database" → "PostgreSQL"
   - Name: `boss-workflow-staging-db`

**Option B: Railway CLI**

```bash
# Create new project
railway init boss-workflow-staging

# Add PostgreSQL
railway add --database postgres

# Link to GitHub repo (staging branch)
railway link
```

---

### 2. Copy Production Database to Staging

**⚠️ IMPORTANT:** Anonymize sensitive data before copying!

```bash
# Step 1: Export production database (sanitized)
railway run -s boss-workflow "pg_dump $DATABASE_URL" > staging_db_dump.sql

# Step 2: Sanitize dump (remove real user data)
# Edit staging_db_dump.sql and replace:
# - Real email addresses with test emails
# - Real OAuth tokens with dummy tokens
# - Task descriptions containing sensitive info

# Step 3: Import to staging
railway run -s boss-workflow-staging "psql $DATABASE_URL < staging_db_dump.sql"
```

**Alternative: Fresh database with test data**

```bash
# Create fresh database and run migrations
railway run -s boss-workflow-staging "alembic upgrade head"

# Insert test OAuth tokens manually
railway run -s boss-workflow-staging "python scripts/create_test_tokens.py"
```

---

### 3. Configure Environment Variables

Copy all production variables to staging, with these changes:

```bash
# Set staging-specific variables
railway variables set -s boss-workflow-staging \
  "ENVIRONMENT=staging" \
  "TELEGRAM_BOT_TOKEN=<staging_bot_token>" \
  "WEBHOOK_BASE_URL=https://boss-workflow-staging.up.railway.app" \
  "ENCRYPTION_KEY=<same_as_production>" \
  "DISCORD_WEBHOOK_URL=<staging_webhook>" \
  "DEBUG=true"

# Copy production variables (adjust as needed)
railway variables set -s boss-workflow-staging \
  "DEEPSEEK_API_KEY=$DEEPSEEK_API_KEY" \
  "GOOGLE_CREDENTIALS_JSON=$GOOGLE_CREDENTIALS_JSON" \
  "GOOGLE_SHEET_ID=<staging_sheet_id>"
```

**Required staging variables:**

| Variable | Value | Notes |
|----------|-------|-------|
| `ENVIRONMENT` | `staging` | Identifies staging env |
| `ENCRYPTION_KEY` | Same as production | Must match for testing |
| `TELEGRAM_BOT_TOKEN` | Staging bot token | Create new bot with @BotFather |
| `DATABASE_URL` | Auto-set by Railway | Staging PostgreSQL |
| `DEBUG` | `true` | Enable verbose logging |

---

### 4. Deploy Code to Staging

**Deploy from feature branch:**

```bash
# Create encryption feature branch
git checkout -b feat/oauth-encryption-week2

# Make encryption changes (Week 2 tasks)
# ... modify oauth.py, etc.

# Deploy to staging
railway up -s boss-workflow-staging

# Or: Auto-deploy from GitHub branch
# Configure in Railway dashboard:
# Settings → Deployments → Branch: feat/oauth-encryption-week2
```

---

### 5. Create Test OAuth Tokens

Create test Google accounts for OAuth testing:

**Test accounts to create:**

1. **test-calendar@gmail.com**
   - Enable Google Calendar API
   - Create test calendars
   - Purpose: Test calendar integration encryption

2. **test-tasks@gmail.com**
   - Enable Google Tasks API
   - Create test task lists
   - Purpose: Test tasks integration encryption

3. **test-gmail@gmail.com**
   - Enable Gmail API
   - Send test emails
   - Purpose: Test Gmail integration encryption

**Insert test tokens:**

```python
# scripts/create_test_tokens.py
import asyncio
from src.database.repositories.oauth import get_oauth_repository

async def create_test_tokens():
    repo = get_oauth_repository()

    # Test tokens (dummy values)
    test_tokens = [
        {
            "email": "test-calendar@gmail.com",
            "service": "calendar",
            "refresh_token": "test_refresh_token_calendar_123",
            "access_token": "test_access_token_calendar_456",
            "expires_in": 3600,
        },
        {
            "email": "test-tasks@gmail.com",
            "service": "tasks",
            "refresh_token": "test_refresh_token_tasks_789",
            "access_token": "test_access_token_tasks_012",
            "expires_in": 3600,
        },
        {
            "email": "test-gmail@gmail.com",
            "service": "gmail",
            "refresh_token": "test_refresh_token_gmail_345",
            "access_token": "test_access_token_gmail_678",
            "expires_in": 3600,
        },
    ]

    for token_data in test_tokens:
        await repo.store_token(**token_data)
        print(f"✅ Created test token for {token_data['email']}")

if __name__ == "__main__":
    asyncio.run(create_test_tokens())
```

Run in staging:
```bash
railway run -s boss-workflow-staging "python scripts/create_test_tokens.py"
```

---

## Testing Checklist

### Phase 1: Basic Encryption Tests

- [ ] **Verify encryption initialization**
  ```bash
  railway logs -s boss-workflow-staging | grep "Token encryption initialized"
  # Expected: "Token encryption initialized successfully"
  ```

- [ ] **Test token storage (encrypted)**
  ```python
  # Test with Telegram bot in staging
  # Send OAuth setup flow: /oauth_setup
  # Check database: tokens should be encrypted (start with "gAAAAA")
  ```

- [ ] **Test token retrieval (decrypted)**
  ```python
  # Trigger Calendar/Tasks integration
  # Verify: Token decrypts correctly, API calls succeed
  ```

- [ ] **Verify database storage format**
  ```sql
  -- Run in staging database
  SELECT email, service,
         LEFT(refresh_token, 10) as token_prefix,
         LENGTH(refresh_token) as token_length
  FROM oauth_tokens;

  -- Expected: token_prefix starts with "gAAAAA", length > 100
  ```

---

### Phase 2: Integration Tests

#### Calendar Integration

- [ ] **Create calendar event with encrypted token**
  ```bash
  # Via Telegram staging bot:
  # "Schedule meeting with team tomorrow at 10am"
  # Check: Event created in test calendar
  ```

- [ ] **List calendar events**
  ```bash
  # Via Telegram: "/calendar today"
  # Check: Events retrieved and displayed
  ```

- [ ] **Token refresh flow**
  ```bash
  # Manually expire access token in DB
  # Trigger calendar action
  # Check: Token auto-refreshes, action succeeds
  ```

#### Tasks Integration

- [ ] **Create task with encrypted token**
  ```bash
  # Via Telegram: "Add task: Test OAuth encryption"
  # Check: Task created in Google Tasks
  ```

- [ ] **List tasks**
  ```bash
  # Via Telegram: "/tasks"
  # Check: Tasks retrieved and displayed
  ```

#### Gmail Integration

- [ ] **Send email digest with encrypted token**
  ```bash
  # Manually trigger email digest
  railway run -s boss-workflow-staging "python scripts/send_test_digest.py"
  # Check: Email sent successfully
  ```

---

### Phase 3: Edge Case Tests

- [ ] **Handle missing encryption key**
  ```bash
  # Temporarily unset ENCRYPTION_KEY
  railway variables unset -s boss-workflow-staging "ENCRYPTION_KEY"
  railway redeploy -s boss-workflow-staging --yes

  # Expected: Warning logged, tokens stored as plaintext
  # Restore key after test
  ```

- [ ] **Handle corrupted encrypted token**
  ```sql
  -- Corrupt a token in database
  UPDATE oauth_tokens
  SET refresh_token = 'corrupted_token_xyz'
  WHERE email = 'test-calendar@gmail.com';

  -- Trigger calendar action
  -- Expected: Graceful error, fallback to plaintext assumption
  ```

- [ ] **Backward compatibility (plaintext tokens)**
  ```sql
  -- Insert plaintext token
  INSERT INTO oauth_tokens (email, service, refresh_token, access_token)
  VALUES ('test-legacy@gmail.com', 'calendar', 'plaintext_token_123', 'plaintext_access');

  -- Retrieve token
  -- Expected: Returns plaintext token as-is (no decrypt error)
  ```

---

### Phase 4: Performance Tests

- [ ] **Encryption overhead measurement**
  ```python
  # scripts/benchmark_encryption.py
  import time
  from src.utils.encryption import get_token_encryption

  enc = get_token_encryption()
  test_token = "test_token_" * 10

  # Benchmark encrypt
  start = time.time()
  for _ in range(1000):
      enc.encrypt(test_token)
  encrypt_time = (time.time() - start) * 1000
  print(f"Encrypt 1000 tokens: {encrypt_time:.2f}ms ({encrypt_time/1000:.2f}ms each)")

  # Benchmark decrypt
  encrypted = enc.encrypt(test_token)
  start = time.time()
  for _ in range(1000):
      enc.decrypt(encrypted)
  decrypt_time = (time.time() - start) * 1000
  print(f"Decrypt 1000 tokens: {decrypt_time:.2f}ms ({decrypt_time/1000:.2f}ms each)")

  # Expected: < 5ms per operation
  ```

- [ ] **Bulk token operations**
  ```bash
  # Create 100 test tokens
  railway run -s boss-workflow-staging "python scripts/create_bulk_test_tokens.py"

  # Retrieve all tokens
  railway run -s boss-workflow-staging "python scripts/retrieve_all_tokens.py"

  # Expected: All operations complete successfully, < 1s total
  ```

---

### Phase 5: Security Validation

- [ ] **Verify tokens encrypted in database**
  ```sql
  SELECT email, service,
         CASE
           WHEN refresh_token LIKE 'gAAAAA%' THEN 'Encrypted ✅'
           ELSE 'Plaintext ❌'
         END as encryption_status
  FROM oauth_tokens;

  -- All should show "Encrypted ✅"
  ```

- [ ] **Verify no plaintext tokens in logs**
  ```bash
  railway logs -s boss-workflow-staging | grep -E "ya29\.|1//|AIza"
  # Expected: No results (no plaintext tokens logged)
  ```

- [ ] **Audit encryption initialization**
  ```bash
  railway logs -s boss-workflow-staging --json | jq '.[] | select(.message | contains("encryption"))'
  # Expected: Only "initialized successfully" messages
  ```

---

## Staging to Production Migration Checklist

Before deploying encryption to production:

- [ ] All 25+ tests above passed
- [ ] Zero errors in staging logs (last 24 hours)
- [ ] Performance metrics acceptable (< 5ms overhead)
- [ ] Backward compatibility verified (plaintext tokens work)
- [ ] Security validation complete (no token leaks)
- [ ] Team review of staging test results
- [ ] Production backup complete (run `backup_oauth_tokens.py`)
- [ ] Production deployment plan documented
- [ ] Rollback procedure tested in staging

---

## Rollback Procedure

If issues found in staging:

1. **Revert code changes:**
   ```bash
   git revert <commit_hash>
   railway up -s boss-workflow-staging
   ```

2. **Restore database backup:**
   ```bash
   railway run -s boss-workflow-staging "psql $DATABASE_URL < staging_db_backup.sql"
   ```

3. **Investigate errors:**
   ```bash
   railway logs -s boss-workflow-staging --tail 1000 > staging_errors.log
   # Analyze logs for root cause
   ```

---

## Monitoring and Alerting

### Key Metrics to Monitor

```python
# Monitor these in staging logs
metrics = {
    "encryption_init_success": True,  # Must be True
    "encryption_errors": 0,            # Must be 0
    "decryption_failures": 0,          # Must be 0
    "token_access_count": "> 0",       # Should have activity
    "avg_encrypt_time_ms": "< 5",      # Performance target
    "avg_decrypt_time_ms": "< 5",      # Performance target
}
```

### Alerts to Configure

```bash
# Set up Railway log alerts (if available)
# Alert on:
# - "Failed to initialize token encryption"
# - "Failed to encrypt token"
# - "Failed to decrypt token" (unless plaintext fallback)
# - Any ERROR level logs related to OAuth
```

---

## Test Data Cleanup

After staging testing complete:

```sql
-- Clean up test tokens
DELETE FROM oauth_tokens WHERE email LIKE 'test-%@gmail.com';

-- Clean up test tasks
DELETE FROM tasks WHERE title LIKE 'Test OAuth%';

-- Verify cleanup
SELECT COUNT(*) FROM oauth_tokens;  -- Should be 0 or only real tokens
```

---

## Additional Resources

- Week 2 implementation: See `CLAUDE.md` Week 2 section
- Encryption utilities: `src/utils/encryption.py`
- OAuth repository: `src/database/repositories/oauth.py`
- Railway staging docs: https://docs.railway.app/develop/environments

---

*Last updated: 2026-01-24*
*Next review: After Week 2 implementation*
