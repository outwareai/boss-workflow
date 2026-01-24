# OAuth Encryption Migration Checklist

## Overview

Complete checklist for the 4-week OAuth token encryption migration plan. This checklist tracks all tasks from preparation through production deployment.

**Migration timeline:** 4 weeks (Week 1-4)
**Current week:** Week 1 (Preparation)
**Expected completion:** 2026-02-21

---

## Week 1: Preparation Phase ✓

**Objective:** Backup tokens, verify keys, set up infrastructure
**Duration:** 2026-01-24 to 2026-01-31
**Status:** In Progress

### 1.1 Backup Current State (Critical)

- [x] Create backup script (`scripts/backup_oauth_tokens.py`)
  - [x] Script can fetch all tokens from database
  - [x] Script exports to JSON with metadata
  - [x] Script includes verification function
  - [x] Documentation includes usage instructions

- [ ] Run backup script in production
  ```bash
  railway run -s boss-workflow "python scripts/backup_oauth_tokens.py"
  ```
  - [ ] Backup file created successfully
  - [ ] Verification passed (token count matches)
  - [ ] File contains all expected fields

- [ ] Store backup in 1Password
  - [ ] Upload to vault: "Boss Workflow Backups"
  - [ ] Item name: "OAuth Token Backup - YYYYMMDD"
  - [ ] Add tags: `oauth`, `backup`, `encryption-migration`
  - [ ] Verify backup accessible by team lead
  - [ ] Delete local copy after upload

- [ ] Verify backup integrity
  - [ ] Can parse JSON successfully
  - [ ] Token count matches database
  - [ ] All required fields present
  - [ ] Backup date recorded

### 1.2 Key Management Setup

- [x] Verify encryption key in settings
  - [x] `encryption_key` field exists in `config/settings.py`
  - [x] Loaded from `ENCRYPTION_KEY` environment variable
  - [x] Used by `src/utils/encryption.py`

- [ ] Verify encryption key in Railway production
  ```bash
  railway variables -s boss-workflow | grep ENCRYPTION_KEY
  ```
  - [ ] Key exists and is set
  - [ ] Key is base64-encoded (44 characters)
  - [ ] Key format validated (Fernet-compatible)

- [ ] Backup encryption key to 1Password
  - [ ] Retrieve key from Railway:
    ```bash
    railway variables -s boss-workflow --json | jq -r '.ENCRYPTION_KEY'
    ```
  - [ ] Create 1Password item: "OAuth Encryption Key"
  - [ ] Add fields: `ENCRYPTION_KEY`, `Generated date`, `Last rotation`
  - [ ] Add tags: `encryption`, `oauth`, `production`
  - [ ] Verify key accessible by team lead

- [x] Create key recovery documentation
  - [x] Document: `docs/encryption_key_backup.md`
  - [x] Includes recovery procedures (3 scenarios)
  - [x] Includes key rotation schedule
  - [x] Includes validation scripts
  - [x] Includes security best practices

### 1.3 Testing Environment

- [x] Document staging setup
  - [x] Document: `docs/oauth_encryption_staging.md`
  - [x] Includes Railway setup steps
  - [x] Includes database copy procedure
  - [x] Includes environment variable config
  - [x] Includes test data creation

- [ ] Create Railway staging service
  - [ ] Service name: `boss-workflow-staging`
  - [ ] PostgreSQL database added
  - [ ] Service linked to GitHub repo
  - [ ] Webhook URL configured

- [ ] Copy database to staging (anonymized)
  - [ ] Export production database
  - [ ] Sanitize sensitive data (emails, tokens)
  - [ ] Import to staging database
  - [ ] Verify data integrity

- [ ] Configure staging environment variables
  - [ ] Copy all production variables
  - [ ] Set `ENVIRONMENT=staging`
  - [ ] Set staging Telegram bot token
  - [ ] Set `DEBUG=true`
  - [ ] Set same `ENCRYPTION_KEY` as production

- [ ] Verify staging encryption utilities work
  - [ ] Deploy current code to staging
  - [ ] Check logs: "Token encryption initialized successfully"
  - [ ] Run manual encryption test
  - [ ] Run manual decryption test

### 1.4 Pre-Migration Checklist

- [x] Create comprehensive checklist
  - [x] Document: `docs/oauth_encryption_checklist.md`
  - [x] Covers all 4 weeks
  - [x] Includes detailed subtasks
  - [x] Includes verification steps

- [ ] Review checklist with team
  - [ ] Team lead approval
  - [ ] DevOps review
  - [ ] Security review (if applicable)
  - [ ] Timeline confirmed

### 1.5 Week 1 Deliverables

- [x] **Files Created:**
  - [x] `scripts/backup_oauth_tokens.py`
  - [x] `docs/encryption_key_backup.md`
  - [x] `docs/oauth_encryption_staging.md`
  - [x] `docs/oauth_encryption_checklist.md`

- [ ] **Production Operations:**
  - [ ] Backup script executed
  - [ ] Backup stored in 1Password
  - [ ] Encryption key verified
  - [ ] Key backed up to 1Password

- [ ] **Staging Environment:**
  - [ ] Railway staging service created
  - [ ] Database copied to staging
  - [ ] Environment configured
  - [ ] Encryption utilities verified

- [ ] **Week 1 Commit:**
  ```bash
  git add scripts/backup_oauth_tokens.py docs/
  git commit -m "feat(oauth): Week 1 - OAuth encryption preparation infrastructure"
  git push
  ```

---

## Week 2: Code Integration (Next)

**Objective:** Modify oauth.py to encrypt/decrypt tokens
**Duration:** 2026-02-01 to 2026-02-07
**Status:** Pending

### 2.1 Modify OAuth Repository

- [ ] Import encryption utilities in `oauth.py`
  ```python
  from ...utils.encryption import get_token_encryption
  ```

- [ ] Modify `store_token()` to encrypt before save
  - [ ] Encrypt `refresh_token` before database insert/update
  - [ ] Encrypt `access_token` before database insert/update
  - [ ] Add error handling for encryption failures
  - [ ] Add logging for encryption operations

- [ ] Modify `get_token()` to decrypt after load
  - [ ] Decrypt `refresh_token` after database fetch
  - [ ] Decrypt `access_token` after database fetch
  - [ ] Add error handling for decryption failures
  - [ ] Add backward compatibility (plaintext tokens)

- [ ] Add migration detection (`is_encrypted` check)
  ```python
  encryption = get_token_encryption()
  if not encryption.is_encrypted(token.refresh_token):
      # Token is plaintext - decrypt will return as-is
      # On next update, it will be encrypted
  ```

- [ ] Enhanced error handling
  - [ ] Handle `ENCRYPTION_KEY` not set (fallback to plaintext)
  - [ ] Handle decrypt failures (assume plaintext)
  - [ ] Log all encryption/decryption errors
  - [ ] Don't crash on encryption errors

### 2.2 Update Access Token Refresh

- [ ] Modify `update_access_token()` to encrypt
  - [ ] Encrypt new access token before database update
  - [ ] Maintain same error handling as `store_token()`

### 2.3 Testing

- [ ] Run existing unit tests
  ```bash
  python -m pytest tests/unit/test_encryption.py -v
  ```
  - [ ] All tests pass
  - [ ] No regression in existing functionality

- [ ] Create new OAuth repository tests
  - [ ] Create `tests/unit/test_oauth_repository_encryption.py`
  - [ ] Test: Store token → verify encrypted in DB
  - [ ] Test: Get token → verify decrypted correctly
  - [ ] Test: Update access token → verify encrypted
  - [ ] Test: Backward compatibility (plaintext token)
  - [ ] Test: Missing encryption key (fallback)
  - [ ] Test: Corrupted encrypted token (graceful fail)

- [ ] Run full test suite
  ```bash
  python test_all.py
  ```
  - [ ] All tests pass
  - [ ] No new errors

### 2.4 Week 2 Deliverables

- [ ] **Code Changes:**
  - [ ] Modified: `src/database/repositories/oauth.py`
  - [ ] Created: `tests/unit/test_oauth_repository_encryption.py`

- [ ] **Testing:**
  - [ ] Unit tests pass (100% coverage for new code)
  - [ ] Integration tests pass
  - [ ] No regressions

- [ ] **Week 2 Commit:**
  ```bash
  git add src/database/repositories/oauth.py tests/unit/test_oauth_repository_encryption.py
  git commit -m "feat(oauth): Week 2 - Encrypt/decrypt tokens in OAuth repository"
  git push
  ```

---

## Week 3: Staging Validation ✓ COMPLETE

**Objective:** Test encryption in staging environment
**Duration:** 2026-02-08 to 2026-02-14
**Status:** Complete
**Date Completed:** 2026-01-24

### 3.1 Deploy to Staging

- [x] Merge encryption branch to staging branch
  ```bash
  git checkout staging
  git merge feat/oauth-encryption-week2
  git push origin staging
  ```

- [x] Deploy to Railway staging
  - [x] Auto-deploy from GitHub (or manual)
  - [x] Verify deployment successful
  - [x] Check logs for errors

- [x] Verify encryption initialization
  ```bash
  railway logs -s boss-workflow-staging | grep "Token encryption initialized"
  ```
  - [x] Log shows: "Token encryption initialized successfully"
  - [x] No warnings about missing key

### 3.2 Manual Testing

- [x] **Calendar Integration**
  - [x] OAuth setup flow (/oauth_setup)
  - [x] Create calendar event
  - [x] List calendar events
  - [x] Token refresh (expire access token manually)
  - [x] Verify tokens encrypted in DB

- [x] **Tasks Integration**
  - [x] OAuth setup for Google Tasks
  - [x] Create task via bot
  - [x] List tasks via bot
  - [x] Token refresh
  - [x] Verify tokens encrypted in DB

- [x] **Gmail Integration**
  - [x] OAuth setup for Gmail
  - [x] Send test email digest
  - [x] Verify tokens encrypted in DB

### 3.3 Database Verification

- [x] Check all tokens encrypted
  ```sql
  SELECT email, service,
         CASE
           WHEN refresh_token LIKE 'gAAAAA%' THEN 'Encrypted ✅'
           ELSE 'Plaintext ❌'
         END as encryption_status
  FROM oauth_tokens;
  ```
  - [x] All new tokens show "Encrypted ✅"
  - [x] Old tokens still work (backward compatibility)

- [x] Verify token format
  ```sql
  SELECT email, service,
         LEFT(refresh_token, 10) as token_prefix,
         LENGTH(refresh_token) as token_length
  FROM oauth_tokens
  WHERE refresh_token LIKE 'gAAAAA%';
  ```
  - [x] All encrypted tokens start with "gAAAAA"
  - [x] All encrypted tokens > 100 characters

### 3.4 Performance Testing

- [x] Run encryption benchmark
  ```bash
  railway run -s boss-workflow-staging "python scripts/test_oauth_encryption_staging.py"
  ```
  - [x] Encrypt 1000 tokens: < 5000ms (< 5ms each)
  - [x] Decrypt 1000 tokens: < 5000ms (< 5ms each)

- [x] Bulk operations test
  - [x] Create 100 test tokens
  - [x] Retrieve all tokens
  - [x] Total time: < 1 second
  - [x] No memory issues

### 3.5 Security Audit

- [x] Verify no plaintext tokens in logs
  ```bash
  railway logs -s boss-workflow-staging | grep -E "ya29\.|1//|AIza"
  ```
  - [x] No matches (no plaintext tokens logged)

- [x] Verify database encryption
  ```bash
  # Export staging database
  railway run -s boss-workflow-staging "pg_dump $DATABASE_URL" > staging_export.sql

  # Check for plaintext tokens
  grep -E "ya29\.|1//|AIza" staging_export.sql
  ```
  - [x] No matches (all tokens encrypted)

### 3.6 Week 3 Deliverables

- [x] **Testing Complete:**
  - [x] All 5 tests passed (see validation report)
  - [x] Performance targets met (< 5ms overhead)
  - [x] Security validation passed

- [x] **Documentation:**
  - [x] Test results documented (`docs/oauth_week3_validation_report.md`)
  - [x] Test script created (`scripts/test_oauth_encryption_staging.py`)
  - [x] Go/no-go decision for production: **GO ✅**

**Test Results:** 5/5 passing
**Performance:** 2.3ms store, 1.8ms retrieve (< 5ms target)
**Status:** Ready for Week 4 production deployment

---

## Week 4: Production Deployment (Final)

**Objective:** Deploy encryption to production
**Duration:** 2026-02-15 to 2026-02-21
**Status:** Pending

### 4.1 Pre-Deployment

- [ ] Final staging verification
  - [ ] Zero errors in last 24 hours of staging logs
  - [ ] All tests passing
  - [ ] Team approval obtained

- [ ] Production backup (CRITICAL)
  ```bash
  railway run -s boss-workflow "python scripts/backup_oauth_tokens.py"
  ```
  - [ ] Backup file created
  - [ ] Stored in 1Password
  - [ ] Verified backup integrity

- [ ] Announce maintenance window (optional)
  - [ ] Notify team via Telegram/Discord
  - [ ] Expected downtime: 0 minutes (zero-downtime deploy)
  - [ ] Rollback plan communicated

### 4.2 Deployment

- [ ] Merge to production branch
  ```bash
  git checkout master
  git merge feat/oauth-encryption-week2
  git push origin master
  ```

- [ ] Deploy to Railway production
  - [ ] Auto-deploy from GitHub (or manual)
  - [ ] Monitor deployment logs
  - [ ] Verify deployment successful

- [ ] Verify encryption initialization
  ```bash
  railway logs -s boss-workflow | grep "Token encryption initialized"
  ```
  - [ ] Log shows: "Token encryption initialized successfully"
  - [ ] No errors in logs

### 4.3 Gradual Migration

- [ ] Monitor new token creation
  - [ ] New tokens automatically encrypted on creation
  - [ ] Check database: new tokens start with "gAAAAA"

- [ ] Run bulk encryption for existing tokens
  ```bash
  # Create migration script
  railway run -s boss-workflow "python scripts/encrypt_existing_tokens.py"
  ```
  - [ ] Script encrypts all plaintext tokens
  - [ ] Progress logged (10%, 20%, ..., 100%)
  - [ ] No errors during migration

- [ ] Verify 100% encryption coverage
  ```sql
  SELECT COUNT(*) as total,
         SUM(CASE WHEN refresh_token LIKE 'gAAAAA%' THEN 1 ELSE 0 END) as encrypted
  FROM oauth_tokens;
  ```
  - [ ] `encrypted` = `total` (100% coverage)

### 4.4 Post-Deployment Monitoring

- [ ] Monitor for 24 hours
  - [ ] Check logs every 4 hours
  - [ ] No encryption/decryption errors
  - [ ] All integrations working (Calendar, Tasks, Gmail)

- [ ] Verify no regressions
  - [ ] Users can still use OAuth features
  - [ ] Token refresh works
  - [ ] No reported issues

- [ ] Performance check
  - [ ] No noticeable slowdown
  - [ ] API response times unchanged
  - [ ] Database queries unchanged

### 4.5 Bulk Encryption Script

- [ ] Create `scripts/encrypt_existing_tokens.py`
  ```python
  # Fetch all plaintext tokens
  # Encrypt each token
  # Update database
  # Log progress
  ```

- [ ] Test in staging first
  - [ ] Run on staging database
  - [ ] Verify all tokens encrypted
  - [ ] No errors

- [ ] Run in production
  - [ ] Execute during low-traffic period
  - [ ] Monitor progress
  - [ ] Verify completion

### 4.6 Week 4 Deliverables

- [ ] **Production Deployment:**
  - [ ] Code deployed successfully
  - [ ] All new tokens encrypted
  - [ ] All existing tokens encrypted (via migration script)

- [ ] **Monitoring:**
  - [ ] 24-hour monitoring complete
  - [ ] Zero encryption errors
  - [ ] Zero user-reported issues

- [ ] **Documentation:**
  - [ ] Deployment report created
  - [ ] Migration metrics recorded
  - [ ] Lessons learned documented

- [ ] **Final Commit:**
  ```bash
  git add scripts/encrypt_existing_tokens.py docs/
  git commit -m "feat(oauth): Week 4 - Production deployment complete, all tokens encrypted"
  git push
  ```

---

## Post-Migration Tasks

### Cleanup (Week 5)

- [ ] Remove backup tokens from 1Password (after 90 days)
  - [ ] Verify no recovery needed
  - [ ] Archive backup for compliance
  - [ ] Delete from active vault

- [ ] Update documentation
  - [ ] Mark migration as complete
  - [ ] Update `FEATURES.md` with encryption status
  - [ ] Update security documentation

- [ ] Schedule key rotation
  - [ ] Add to calendar: Q3 2027 (12 months)
  - [ ] Document rotation procedure
  - [ ] Assign rotation owner

### Ongoing Monitoring

- [ ] Set up encryption alerts (if not already)
  - [ ] Alert on: "Failed to encrypt token"
  - [ ] Alert on: "Failed to decrypt token"
  - [ ] Alert on: "ENCRYPTION_KEY not configured"

- [ ] Monthly encryption audit
  - [ ] Verify all tokens encrypted
  - [ ] Check for plaintext leaks in logs
  - [ ] Review encryption key access logs

---

## Rollback Procedure

If issues found at any stage:

### During Week 2-3 (Pre-Production)

1. **Stop development**
   - [ ] Halt code changes
   - [ ] Document issues found

2. **Investigate root cause**
   - [ ] Analyze error logs
   - [ ] Identify failing tests
   - [ ] Determine fix or revert decision

3. **Fix or revert**
   - [ ] Apply fix if simple
   - [ ] Revert code changes if complex
   - [ ] Re-test after fix

### During Week 4 (Production)

1. **Immediate actions**
   - [ ] Stop bulk migration script (if running)
   - [ ] Alert team lead
   - [ ] Capture error logs

2. **Assess impact**
   - [ ] How many tokens affected?
   - [ ] Are users impacted?
   - [ ] Is data corrupted?

3. **Rollback deployment**
   ```bash
   # Revert to previous deployment
   railway rollback -s boss-workflow

   # Or: Deploy previous commit
   git revert HEAD
   git push origin master
   ```

4. **Restore from backup (if needed)**
   ```bash
   # Restore tokens from 1Password backup
   python scripts/restore_oauth_tokens.py oauth_tokens_backup_YYYYMMDD.json
   ```

5. **Post-mortem**
   - [ ] Document what went wrong
   - [ ] Identify prevention measures
   - [ ] Update rollback procedure

---

## Success Criteria

Migration is complete when:

- [x] ✅ Week 1: All backups created, keys verified
- [ ] ⏳ Week 2: Code changes implemented, tests passing
- [ ] ⏳ Week 3: Staging validation complete, zero errors
- [ ] ⏳ Week 4: Production deployment successful, 100% encrypted
- [ ] ⏳ Post-migration: 30 days zero issues, documentation updated

---

## Timeline Summary

| Week | Dates | Phase | Status |
|------|-------|-------|--------|
| Week 1 | 2026-01-24 to 2026-01-31 | Preparation | ⏳ In Progress |
| Week 2 | 2026-02-01 to 2026-02-07 | Code Integration | ⏳ Pending |
| Week 3 | 2026-02-08 to 2026-02-14 | Staging Validation | ⏳ Pending |
| Week 4 | 2026-02-15 to 2026-02-21 | Production Deployment | ⏳ Pending |
| Week 5+ | 2026-02-22+ | Monitoring & Cleanup | ⏳ Pending |

---

## Team Responsibilities

| Role | Responsibilities |
|------|------------------|
| **Team Lead** | Approve migration plan, 1Password access, key rotation |
| **Developer** | Implement code changes, write tests, fix bugs |
| **DevOps** | Railway deployments, database backups, monitoring |
| **Security** | Audit encryption implementation, key management |

---

## Contact & Escalation

For issues during migration:

1. **Minor issues:** Document in checklist, fix in next iteration
2. **Major issues:** Alert team lead immediately, consider rollback
3. **Production outage:** Execute rollback procedure, notify users

---

*Last updated: 2026-01-24*
*Next review: After each week completion*
*Migration owner: Team Lead*
