# Encryption Key Backup and Recovery

## Overview

This document outlines the backup and recovery procedures for the OAuth token encryption key used in Boss Workflow.

**Encryption Method:** Fernet (symmetric encryption, AES-128 in CBC mode)
**Key Storage:** Environment variable `ENCRYPTION_KEY`
**Key Format:** Base64-encoded 32-byte key

---

## Key Storage Locations

### Primary Storage

1. **Railway Production Environment**
   - Variable name: `ENCRYPTION_KEY`
   - Access: Railway dashboard → boss-workflow → Variables
   - Managed by: Team lead / DevOps
   - CLI check: `railway variables -s boss-workflow | grep ENCRYPTION_KEY`

2. **1Password Vault (Backup)**
   - Vault: "Boss Workflow"
   - Item: "OAuth Encryption Key"
   - Tags: `encryption`, `oauth`, `production`
   - Fields:
     - `ENCRYPTION_KEY` (password field)
     - `Generated date` (text)
     - `Last rotation` (text)
     - `Next rotation due` (text)

### Offline Backup (Optional, for disaster recovery)

3. **Encrypted Backup File**
   - Filename: `encryption_key_backup_YYYYMMDD.txt.gpg`
   - Location: Secure external storage (not in git)
   - Encryption: GPG with team lead's key
   - Create with:
     ```bash
     echo "$ENCRYPTION_KEY" | gpg --encrypt --recipient team@example.com > encryption_key_backup_$(date +%Y%m%d).txt.gpg
     ```

---

## Recovery Procedures

### Scenario 1: Lost Railway Environment Variable

**Symptom:** Railway deployment shows "ENCRYPTION_KEY not configured" warning

**Recovery Steps:**

1. **Retrieve key from 1Password:**
   ```bash
   # Login to 1Password
   # Navigate to: Boss Workflow → OAuth Encryption Key
   # Copy ENCRYPTION_KEY value
   ```

2. **Set in Railway:**
   ```bash
   # Option A: Railway CLI
   railway variables set -s boss-workflow "ENCRYPTION_KEY=<key_from_1password>"

   # Option B: Railway Dashboard
   # Go to boss-workflow → Variables → Add Variable
   # Name: ENCRYPTION_KEY
   # Value: <paste from 1Password>
   ```

3. **Redeploy:**
   ```bash
   railway redeploy -s boss-workflow --yes
   ```

4. **Verify:**
   ```bash
   # Check logs for: "Token encryption initialized successfully"
   railway logs -s boss-workflow | grep "Token encryption"
   ```

**Recovery Time:** ~5 minutes
**Data Loss:** None (tokens remain encrypted in database)

---

### Scenario 2: Complete Key Loss (All Backups Lost)

**Symptom:** Cannot find encryption key in Railway, 1Password, or backups

**Impact:** **ALL ENCRYPTED TOKENS ARE PERMANENTLY LOST**

**Recovery Steps:**

1. **Generate new encryption key:**
   ```bash
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

2. **Set new key in Railway:**
   ```bash
   railway variables set -s boss-workflow "ENCRYPTION_KEY=<new_key>"
   railway redeploy --yes
   ```

3. **Clear all OAuth tokens from database:**
   ```sql
   -- Run in Railway PostgreSQL console
   DELETE FROM oauth_tokens;
   ```

4. **Notify all users to re-authenticate:**
   - Send notification via Telegram bot
   - Provide OAuth setup instructions
   - Expected re-auth time per user: 5-10 minutes

5. **Update backup locations:**
   - Store new key in 1Password
   - Create new encrypted backup file
   - Update key rotation schedule

**Recovery Time:** 1-2 hours (includes user re-authentication)
**Data Loss:** All OAuth tokens (users must re-authenticate)

---

### Scenario 3: Key Rotation (Planned)

**When:** Every 12 months (see rotation schedule below)

**Steps:**

1. **Backup all tokens with old key:**
   ```bash
   python scripts/backup_oauth_tokens.py
   # Store in 1Password: "OAuth Token Backup - Pre-Rotation YYYYMMDD"
   ```

2. **Generate new key:**
   ```bash
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

3. **Create migration script** (`scripts/rotate_encryption_key.py`):
   ```python
   # Decrypt all tokens with old key
   # Re-encrypt all tokens with new key
   # Update database
   ```

4. **Deploy new key to Railway:**
   ```bash
   railway variables set -s boss-workflow "ENCRYPTION_KEY_NEW=<new_key>"
   ```

5. **Run migration:**
   ```bash
   railway run -s boss-workflow "python scripts/rotate_encryption_key.py"
   ```

6. **Swap keys:**
   ```bash
   railway variables set -s boss-workflow "ENCRYPTION_KEY=<new_key>"
   railway variables unset -s boss-workflow "ENCRYPTION_KEY_NEW"
   railway redeploy --yes
   ```

7. **Update 1Password with new key**

**Recovery Time:** 30-60 minutes
**Data Loss:** None (zero-downtime migration)

---

## Key Rotation Schedule

| Event | Date | Next Due | Status |
|-------|------|----------|--------|
| Initial key generation | 2026-01-24 | - | ✅ Complete |
| First rotation | Q3 2027 | 2027-09-01 | ⏳ Pending |
| Second rotation | Q3 2028 | 2028-09-01 | ⏳ Pending |

**Rotation Policy:** Every 12 months, or immediately if:
- Key compromise suspected
- Security audit recommendation
- Team member with key access leaves company

---

## Key Generation

### Generate a New Key

```bash
# Method 1: Python (Recommended)
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Method 2: Using cryptography library in script
from cryptography.fernet import Fernet
key = Fernet.generate_key()
print(f"New encryption key: {key.decode()}")
```

**Output format:** Base64-encoded string (e.g., `7vZ5wX8jK3mN4pQ6rT9yU2vA5zB8xC1dE4fG7hJ0kL3=`)

**Key length:** 44 characters (32 bytes base64-encoded)

---

## Validation and Testing

### Verify Key Format

```python
from cryptography.fernet import Fernet

def validate_encryption_key(key: str) -> bool:
    """Check if key is valid Fernet key."""
    try:
        Fernet(key.encode())
        return True
    except Exception as e:
        print(f"Invalid key: {e}")
        return False

# Test
key = "your_key_here"
if validate_encryption_key(key):
    print("✅ Key is valid")
else:
    print("❌ Key is invalid")
```

### Test Encryption/Decryption

```python
from src.utils.encryption import get_token_encryption

enc = get_token_encryption()

# Test encrypt/decrypt
test_token = "test_token_12345"
encrypted = enc.encrypt(test_token)
decrypted = enc.decrypt(encrypted)

assert decrypted == test_token, "Encryption/decryption failed"
print("✅ Encryption test passed")
```

---

## Security Best Practices

### DO ✅

- Store encryption key in environment variables (never in code)
- Keep 1Password backup up-to-date
- Rotate key annually
- Use separate keys for dev/staging/production
- Monitor encryption initialization logs
- Audit key access (who has 1Password access)

### DON'T ❌

- Commit encryption key to git
- Share key via email/Slack/Discord
- Store key in plaintext files
- Use same key across multiple projects
- Skip key rotation schedule
- Grant 1Password access to external contractors without review

---

## Emergency Contacts

| Role | Contact | Responsibility |
|------|---------|----------------|
| Team Lead | - | Key rotation, 1Password access |
| DevOps | - | Railway deployment, backup verification |
| Security Lead | - | Key compromise response |

---

## Compliance and Auditing

### Encryption Standards

- **Algorithm:** Fernet (AES-128-CBC + HMAC-SHA256)
- **Key size:** 128-bit symmetric key
- **Compliance:** Meets OWASP token storage guidelines

### Audit Log

All encryption key changes should be logged:

```markdown
## Key Change Log

### 2026-01-24 - Initial Key Setup
- Action: Generated first encryption key
- Reason: OAuth encryption migration (Week 1)
- Changed by: Team Lead
- Verified by: DevOps
- Backup location: 1Password

### 2027-09-01 - First Rotation (Planned)
- Action: Rotate to new key
- Reason: Scheduled annual rotation
- Changed by: TBD
- Verified by: TBD
- Backup location: 1Password
```

---

## Additional Resources

- [Cryptography Library Docs](https://cryptography.io/en/latest/fernet/)
- [Fernet Specification](https://github.com/fernet/spec/blob/master/Spec.md)
- [OWASP Token Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
- Railway CLI Docs: https://docs.railway.app/reference/cli-api
- 1Password CLI: https://developer.1password.com/docs/cli/

---

*Last updated: 2026-01-24*
*Next review: 2026-06-01*
