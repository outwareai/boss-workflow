# Production Validation Checklist - Slowapi Rate Limiting

## Pre-Deployment Validation

### Code & Dependencies
- [x] Slowapi library installed: `pip show slowapi` ✅
- [x] Slowapi middleware implemented: `src/middleware/slowapi_limiter.py` ✅
- [x] Feature flag configured: `config/settings.py` with `USE_SLOWAPI_RATE_LIMITING` ✅
- [x] Exception handler implemented in `src/main.py` ✅
- [x] Monitoring metrics defined ✅
- [ ] All tests passing locally

**Test Command:**
```bash
cd /c/Users/User/Desktop/ACCWARE.AI/AUTOMATION/boss-workflow
python -m pytest tests/unit/test_slowapi_limiter.py -v
```

### Redis Backend
- [ ] Redis accessible locally: `redis-cli ping`
- [ ] Redis URL configured: `REDIS_URL=redis://...`
- [ ] Redis version compatible: 5.0+
- [ ] Memory sufficient: 512MB recommended

**Test Commands:**
```bash
# Test Redis connection
redis-cli -u $REDIS_URL ping

# Check Redis memory
redis-cli -u $REDIS_URL info memory
```

### Railway Configuration
- [ ] Railway PostgreSQL active: `railway databases list`
- [ ] Railway Redis add-on enabled (if using Railway Redis)
- [ ] Environment variables ready for deployment
- [ ] Rollback procedure documented

---

## Deployment Execution

### Step 1: Commit Code Changes
```bash
git add .
git commit -m "feat(rate-limit): Enable slowapi in production with monitoring"
git push
```

**Expected:** Railway auto-deploys within 2 minutes

### Step 2: Set Railway Environment Variables

```bash
# Verify Railway CLI is installed
which railway

# Login to Railway
railway login

# Select project
railway select -p boss-workflow

# View current variables
railway variables -s boss-workflow | head -20

# Enable slowapi
railway variables set USE_SLOWAPI_RATE_LIMITING=true -s boss-workflow

# Configure rate limits
railway variables set RATE_LIMIT_AUTHENTICATED="100/minute" -s boss-workflow
railway variables set RATE_LIMIT_PUBLIC="20/minute" -s boss-workflow

# Verify variables set
railway variables -s boss-workflow | grep -i rate
```

**Expected Output:**
```
RATE_LIMIT_AUTHENTICATED=100/minute
RATE_LIMIT_PUBLIC=20/minute
USE_SLOWAPI_RATE_LIMITING=true
```

---

## Post-Deployment Validation (First Hour)

### ✅ Health Check
```bash
# Should return 200 and healthy status
curl https://boss-workflow-production.up.railway.app/health

# Expected response:
# {
#   "status": "healthy",
#   "services": { ... }
# }
```

### ✅ Rate Limit Headers Present
```bash
# Check that rate limit headers are in response
curl -I https://boss-workflow-production.up.railway.app/api/db/tasks

# Should see headers like:
# X-RateLimit-Limit: 100
# X-RateLimit-Remaining: 99
# X-RateLimit-Reset: 1234567890
```

### ✅ Metrics Available
```bash
# Check that metrics endpoint is working
curl https://boss-workflow-production.up.railway.app/metrics | grep -i rate_limit

# Should see rate limiting metrics
```

### ✅ Check Application Logs
```bash
# Watch for any rate limiting errors
railway logs -s boss-workflow -f --lines 50 | grep -i "rate\|slow\|redis"

# Expected patterns:
# "Slowapi rate limiting enabled"
# "Rate limit exceeded" (only after testing)
```

### ✅ Manual Rate Limit Test

**Test Public Rate Limit (20/minute):**
```bash
# Send 25 rapid requests to public endpoint
# Should succeed up to 20, fail on 21-25

success_count=0
fail_count=0

for i in {1..25}; do
  response=$(curl -s -o /dev/null -w "%{http_code}" \
    https://boss-workflow-production.up.railway.app/api/db/tasks)

  if [ "$response" == "200" ] || [ "$response" == "429" ]; then
    if [ "$response" == "200" ]; then
      ((success_count++))
    else
      ((fail_count++))
    fi
    echo "Request $i: $response"
  fi
done

echo "Summary: $success_count succeeded, $fail_count rate limited"
# Expected: ~20 succeeded, ~5 rate limited (429)
```

**Test Authenticated Rate Limit (100/minute):**
```bash
# With API key header (if available for testing)
for i in {1..105}; do
  response=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "X-API-Key: test-key-123" \
    https://boss-workflow-production.up.railway.app/api/db/tasks)
  echo "Request $i: $response"
done
# Expected: ~100 succeeded, ~5 rate limited (429)
```

---

## 24-Hour Validation

### Monitor Logs for Patterns
```bash
# Check for excessive rate limit violations
railway logs -s boss-workflow -f --lines 200 | \
  grep -c "rate limit\|429" | \
  awk '{if($1 > 10) print "⚠️  High violation rate"; else print "✅ Normal violation rate"}'

# Check for Redis errors
railway logs -s boss-workflow -f --lines 200 | \
  grep -i "redis\|connection" | \
  wc -l
# Expected: 0 errors

# Check for slowapi initialization
railway logs -s boss-workflow -f --lines 200 | \
  grep "Slowapi rate limiting enabled"
```

### Query Prometheus Metrics
```bash
# Check rate limit violations by endpoint
curl https://boss-workflow-production.up.railway.app/metrics | \
  grep 'rate_limit_violations_total'

# Check response time impact
curl https://boss-workflow-production.up.railway.app/metrics | \
  grep 'endpoint_response_time'
```

### Monitor Key Endpoints
```bash
# Test main API endpoints still working
echo "Testing /health..."
curl -s https://boss-workflow-production.up.railway.app/health | jq .status

echo "Testing /api/db/tasks..."
curl -s https://boss-workflow-production.up.railway.app/api/db/tasks | jq '.[0]' | head -5

echo "Testing /webhook/telegram..."
# (Can't fully test without webhook, but should not 429)
curl -I https://boss-workflow-production.up.railway.app/webhook/telegram
```

### User Feedback Check
- [ ] Check Telegram for bot responsiveness
- [ ] Send test task to bot
- [ ] Verify task creation still works
- [ ] Check Discord for messages
- [ ] Verify no rate limit errors in user-facing logs

---

## Week 1 Monitoring

### Daily Checks (9 AM Thailand Time)
```bash
#!/bin/bash
# save as scripts/daily_rate_limit_check.sh

echo "=== Daily Rate Limit Check ==="
echo "Timestamp: $(date)"

# Get violation count from last 24 hours
violations=$(railway logs -s boss-workflow --lines 5000 | \
  grep -c "rate limit\|RateLimitExceeded")
echo "Rate limit violations (24h): $violations"

# Check for Redis errors
redis_errors=$(railway logs -s boss-workflow --lines 5000 | \
  grep -c -i "redis.*error\|redis.*fail")
echo "Redis errors (24h): $redis_errors"

# Sample response time
echo "Sampling response time..."
time curl -s https://boss-workflow-production.up.railway.app/health > /dev/null

# Check Telegram bot responsiveness
echo "Bot responsive: (manual check needed)"

echo "=== Check Complete ==="
```

### Metrics to Record

| Metric | Day 1 | Day 2 | Day 3 | Day 4 | Day 5 | Day 6 | Day 7 |
|--------|-------|-------|-------|-------|-------|-------|-------|
| Violations | ____ | ____ | ____ | ____ | ____ | ____ | ____ |
| Redis Errors | ____ | ____ | ____ | ____ | ____ | ____ | ____ |
| User Complaints | ____ | ____ | ____ | ____ | ____ | ____ | ____ |
| False Positives | ____ | ____ | ____ | ____ | ____ | ____ | ____ |
| P95 Response (ms) | ____ | ____ | ____ | ____ | ____ | ____ | ____ |

### Critical Issues Checklist

If ANY of these occur, **immediately rollback:**

- [ ] Redis backend down (0 successful connections for 5+ minutes)
- [ ] > 100 violations per hour with legitimate users complaining
- [ ] Response time increase > 20ms (indicating middleware overhead)
- [ ] P95 latency degradation > 10% from baseline
- [ ] Cascading failures in dependent services
- [ ] > 5 user reports of being "blocked" by rate limit

**Immediate Rollback Command:**
```bash
railway variables set USE_SLOWAPI_RATE_LIMITING=false -s boss-workflow
```

---

## Week 1 Decision Framework

### IF: Violations = 0
**Status:** ✅ Excellent
**Action:** Continue monitoring, limits may be conservative but that's safe

### IF: Violations = 1-5 per day
**Status:** ✅ Excellent
**Action:** Limits are well-calibrated, continue monitoring

### IF: Violations = 10-50 per day
**Status:** ⚠️ Investigate
- [ ] Are violations from specific endpoint/IP?
- [ ] Are they malicious or legitimate?
- [ ] Need to increase limits or add exemptions?
**Action:** Review logs, decide on adjustment

### IF: Violations > 100 per day
**Status:** 🔴 Critical
- [ ] Check if under attack
- [ ] Check if legitimate surge (new feature, testing)
- [ ] Consider temporary disable while investigating
**Action:** Investigate immediately, may need rollback

### IF: User Complaints = 1+
**Status:** 🔴 Critical
- [ ] Get details from user
- [ ] Check if rate limited legitimately
- [ ] Consider whitelist/exemption
- [ ] May indicate limits too aggressive
**Action:** Investigate, adjust or rollback

---

## Go/No-Go Decision (End of Week 1)

### ✅ GO Decision (Continue with slowapi)
**Criteria - ALL must be true:**
- [ ] Violations < 50/day
- [ ] Redis error rate < 1%
- [ ] Response time impact < 5ms
- [ ] User complaints = 0
- [ ] False positive rate < 1%

**Action:** Move to Phase 2 (limit adjustment)

### 🔴 NO-GO Decision (Rollback to custom middleware)
**Criteria - ANY is true:**
- [ ] Violations > 100/day
- [ ] Redis errors > 10/hour
- [ ] Response time impact > 10ms
- [ ] User complaints > 2
- [ ] False positive rate > 5%

**Action:** Disable with `USE_SLOWAPI_RATE_LIMITING=false`, investigate issues

### ⏸️ INVESTIGATE Decision (Extend Week 1)
**Criteria - Uncertain status:**
- [ ] Violations in gray zone (50-100/day)
- [ ] Some user feedback, investigating
- [ ] Metrics unclear
- [ ] Need more data

**Action:** Extend monitoring another 3-5 days before final decision

---

## Deployment Success Criteria

**This deployment is SUCCESSFUL if:**

✅ All code deployed without errors
✅ No database migration issues
✅ Slowapi initialized correctly
✅ Rate limit headers present in responses
✅ Monitoring metrics accessible
✅ No user complaints in first 24 hours
✅ Violations < 10/day in first 24 hours
✅ Redis backend stable

**This deployment is FAILED if:**

❌ Deployment fails (rollback automatically)
❌ Health check fails post-deployment
❌ Rate limiting blocking legitimate users (> 5 complaints)
❌ Critical performance degradation
❌ Redis backend connection issues
❌ Monitoring metrics not working

---

## Post-Validation Sign-Off

**Deployment Date:** _____________

**Validated By:** _____________

**Status:** ☐ GO | ☐ NO-GO | ☐ INVESTIGATE

**Notes:**
```
________________________________________________________________________
________________________________________________________________________
________________________________________________________________________
```

**Follow-up Actions:**
```
________________________________________________________________________
________________________________________________________________________
```

---

*Last Updated: 2026-01-25*
*Next Validation: 2026-02-01*
