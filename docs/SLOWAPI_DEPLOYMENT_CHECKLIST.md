# Slowapi Rate Limiting - Deployment Checklist

**Deployment Date:** ________________
**Deployed By:** ________________
**Status:** ☐ Not Started | ☐ In Progress | ☐ Complete

---

## Pre-Deployment Phase (Code Ready)

### Code Changes
- [x] Exception handler added to `src/main.py`
- [x] Prometheus metrics created in `src/monitoring/prometheus.py`
- [x] Monitoring exports updated in `src/monitoring/__init__.py`
- [x] Tests added to `tests/unit/test_slowapi_limiter.py`
- [x] Documentation created:
  - [x] `docs/SLOWAPI_ROLLOUT.md` - Phased rollout plan
  - [x] `docs/PRODUCTION_VALIDATION.md` - Validation procedures
  - [x] `docs/SLOWAPI_DEPLOYMENT_CHECKLIST.md` - This file
- [x] Deployment script created: `scripts/enable_slowapi_production.sh`

### Local Testing
- [ ] Run unit tests: `pytest tests/unit/test_slowapi_limiter.py -v`
- [ ] Start local server: `python -m src.main`
- [ ] Verify health check: `curl http://localhost:8000/health`
- [ ] Verify metrics endpoint: `curl http://localhost:8000/metrics | grep rate_limit`

**Test Results:**
```
________________________________________________________________________
________________________________________________________________________
```

### Code Review
- [ ] Code changes reviewed by team lead
- [ ] No merge conflicts
- [ ] All imports resolve correctly
- [ ] No syntax errors

---

## Deployment Phase (Pushing to Production)

### Step 1: Prepare Code
```bash
# Verify clean working directory
git status

# Expected: All changes are staged and ready
```

**Status:** ☐ Ready

### Step 2: Commit Changes
```bash
git add .
git commit -m "feat(rate-limit): Enable slowapi in production with monitoring

- Add slowapi rate limiting exception handler in main.py
- Add Prometheus metrics for rate limit violations
- Add monitoring for Redis backend performance
- Add feature flag metric for slowapi status
- Create production validation and rollout documentation
- Add deployment automation script"

git push
```

**Commit Hash:** ________________
**Status:** ☐ Complete

### Step 3: Wait for Railway Auto-Deploy
Railway auto-deploys on git push to master (takes 2-3 minutes)

**Deploy Status:**
- [ ] Railway deployment triggered (check Railway dashboard)
- [ ] Deployment completed successfully
- [ ] No build errors in logs

**Timeline:**
- Push time: ________________
- Deploy start: ________________
- Deploy complete: ________________

**Status:** ☐ Complete

### Step 4: Verify Deployment via CLI
```bash
# Check deployment status
railway status -s boss-workflow

# Check recent logs
railway logs -s boss-workflow --lines 50 | grep -i "slowapi\|rate"

# Expected output: "Slowapi rate limiting enabled"
```

**Status:** ☐ Complete

---

## Post-Deployment Validation (Hour 1)

### Health Checks
```bash
# 1. Root endpoint
curl https://boss-workflow-production.up.railway.app/
# Expected: {"status": "healthy", ...}
STATUS: ☐ PASS | ☐ FAIL

# 2. Health detail endpoint
curl https://boss-workflow-production.up.railway.app/health
# Expected: 200 status, healthy services
STATUS: ☐ PASS | ☐ FAIL

# 3. Rate limit headers present
curl -I https://boss-workflow-production.up.railway.app/api/db/tasks | grep -i "X-RateLimit"
# Expected: X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset
STATUS: ☐ PASS | ☐ FAIL

# 4. Metrics endpoint
curl https://boss-workflow-production.up.railway.app/metrics | grep "rate_limit_violations_total\|rate_limit_near_limit"
# Expected: Metrics available
STATUS: ☐ PASS | ☐ FAIL
```

### Application Logs Check
```bash
# Watch for any slowapi initialization errors
railway logs -s boss-workflow -f --lines 100 | grep -i "error\|fail\|warn"

# Expected: No rate limiting errors, only normal warnings
STATUS: ☐ PASS | ☐ FAIL
```

### Manual Rate Limit Test (Optional)

**Test Public Rate Limit (20/minute):**
```bash
success=0; fail=0
for i in {1..25}; do
  code=$(curl -s -o /dev/null -w "%{http_code}" \
    https://boss-workflow-production.up.railway.app/api/db/tasks)
  [ "$code" = "200" ] && ((success++)) || ((fail++))
  [ $((i % 5)) -eq 0 ] && echo "Request $i: Success=$success Blocked=$fail"
done
# Expected: ~20 success, ~5 blocked (429)
```

**Result:** Success: ____ Blocked: ____
**STATUS:** ☐ PASS | ☐ FAIL

### Telegram Bot Test
- [ ] Send test message to bot: "Create task: test feature"
- [ ] Bot responds normally without rate limit errors
- [ ] Task created successfully in database

**STATUS:** ☐ PASS | ☐ FAIL

### Discord Integration Test
- [ ] Check that Discord messages are still being posted
- [ ] Verify no rate limit warnings in Discord

**STATUS:** ☐ PASS | ☐ FAIL

---

## Week 1 Monitoring (Jan 25 - Jan 31)

### Daily Check Template

**Date: ___________**

```
Time: ___________
Violations (24h): _____
Redis Errors (24h): _____
User Complaints: _____
Bot Response Time: _____ms
Status: ☐ NORMAL | ☐ INVESTIGATE | ☐ CRITICAL
Notes: ___________________________________________________________________
```

**Day 1 (Jan 25):**
- Time: _____ Violations: _____ Errors: _____ Complaints: _____
- [ ] Logs reviewed
- [ ] Metrics healthy
- [ ] Users report normal

**Day 2 (Jan 26):**
- Time: _____ Violations: _____ Errors: _____ Complaints: _____
- [ ] Logs reviewed
- [ ] Metrics healthy
- [ ] Users report normal

**Day 3 (Jan 27):**
- Time: _____ Violations: _____ Errors: _____ Complaints: _____
- [ ] Logs reviewed
- [ ] Metrics healthy
- [ ] Users report normal

**Day 4 (Jan 28):**
- Time: _____ Violations: _____ Errors: _____ Complaints: _____
- [ ] Logs reviewed
- [ ] Metrics healthy
- [ ] Users report normal

**Day 5 (Jan 29):**
- Time: _____ Violations: _____ Errors: _____ Complaints: _____
- [ ] Logs reviewed
- [ ] Metrics healthy
- [ ] Users report normal

**Day 6 (Jan 30):**
- Time: _____ Violations: _____ Errors: _____ Complaints: _____
- [ ] Logs reviewed
- [ ] Metrics healthy
- [ ] Users report normal

**Day 7 (Jan 31):**
- Time: _____ Violations: _____ Errors: _____ Complaints: _____
- [ ] Logs reviewed
- [ ] Metrics healthy
- [ ] Users report normal

---

## Week 1 Decision Point (Friday, Jan 31)

### Metrics Summary
| Metric | Target | Actual | Status |
|--------|--------|--------|--------|
| Violations/day | < 50 | ____ | ☐ PASS |
| Redis errors | 0 | ____ | ☐ PASS |
| User complaints | 0 | ____ | ☐ PASS |
| P95 latency impact | < 5ms | ____ ms | ☐ PASS |

### Decision
- [ ] **GO** - All metrics excellent, proceed with Phase 2
- [ ] **GO with caution** - Minor issues, increase monitoring, adjust limits
- [ ] **INVESTIGATE** - Some metrics borderline, extend monitoring 3 more days
- [ ] **ROLLBACK** - Critical issues, disable slowapi and revert to custom middleware

**Rationale:**
```
________________________________________________________________________
________________________________________________________________________
________________________________________________________________________
```

### Rollback Procedure (If Needed)
```bash
# Instant rollback with one command
railway variables set USE_SLOWAPI_RATE_LIMITING=false -s boss-workflow

# No code deployment needed - app will auto-switch on next request
# Monitor logs: railway logs -s boss-workflow -f
# Expected: "Custom rate limiting middleware enabled (default)"
```

**Rollback executed:** ☐ Yes | ☐ No
**Time to rollback:** __________ minutes
**Reason:** ___________________________________________________________________

---

## Issues & Resolutions

### Issue 1: _________________________________
**Date:** __________
**Severity:** ☐ Low | ☐ Medium | ☐ High | ☐ Critical
**Description:**
```
________________________________________________________________________
________________________________________________________________________
```

**Resolution:**
```
________________________________________________________________________
```
**Resolved:** ☐ Yes | ☐ No | ☐ Escalated

---

### Issue 2: _________________________________
**Date:** __________
**Severity:** ☐ Low | ☐ Medium | ☐ High | ☐ Critical
**Description:**
```
________________________________________________________________________
________________________________________________________________________
```

**Resolution:**
```
________________________________________________________________________
```
**Resolved:** ☐ Yes | ☐ No | ☐ Escalated

---

## Sign-Off

### Deployment Completed
- [x] Code committed and pushed
- [x] Railway deployment successful
- [x] Health checks passing
- [x] Initial monitoring in place
- [x] Team notified of changes

**Deployment Sign-Off:**

Deployed By: _________________ Date: _________ Time: _________

Verified By: _________________ Date: _________ Time: _________

**Overall Status:**

☐ Successful - Slowapi rate limiting active in production
☐ Partial - Slowapi enabled but with issues (document above)
☐ Rolled Back - Reverted to custom middleware (document reason above)

---

## Post-Deployment Notes

**What Worked Well:**
```
________________________________________________________________________
________________________________________________________________________
```

**What Could Be Improved:**
```
________________________________________________________________________
________________________________________________________________________
```

**Next Steps:**
```
________________________________________________________________________
________________________________________________________________________
```

**Documentation Updates Needed:**
```
________________________________________________________________________
```

---

**For detailed guidance, see:**
- Rollout plan: `docs/SLOWAPI_ROLLOUT.md`
- Validation procedures: `docs/PRODUCTION_VALIDATION.md`
- Slowapi docs: https://slowapi.readthedocs.io/

*Last Updated: 2026-01-25*
