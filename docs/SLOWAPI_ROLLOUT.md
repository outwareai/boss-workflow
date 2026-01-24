# Slowapi Rate Limiting Rollout Plan

## Overview
This document tracks the phased rollout of slowapi rate limiting to production, with a feature flag-based gradual deployment strategy.

---

## Phase 1: Enable in Production (Week 1)

**Timeline:** Week of January 25, 2026

**Actions:**
- ✅ Feature flag enabled: `USE_SLOWAPI_RATE_LIMITING=true`
- ✅ Rate limits configured:
  - Authenticated requests: 100/minute
  - Public requests: 20/minute
- ✅ Metrics and monitoring enabled
- Monitor for 7 days

**Monitoring Focus:**
- Track rate limit violation count by endpoint
- Identify false positives (legitimate users blocked)
- Measure response time impact
- Monitor Redis connection health

**Key Metrics to Track:**
```
rate_limit_violations_total         # Total violations by endpoint
rate_limit_near_limit               # Users approaching limit
endpoint_response_time_ms           # P95/P99 latency impact
redis_connection_health             # Redis backend health
```

**Success Criteria:**
- No unexpected violations (< 5 violations/day)
- False positive rate < 2%
- P95 response time impact < 5ms
- Zero Redis connection errors

---

## Phase 2: Adjust Limits (Week 2)

**Timeline:** Week of February 1, 2026

**Analysis of Week 1 Data:**
- [ ] Total violations: _____
- [ ] Unique users affected: _____
- [ ] Most violated endpoint: _____
- [ ] False positives reported: _____
- [ ] Response time impact: _____ms

**Decision Logic:**
```
IF violations == 0:
  → Limits may be too high, consider reducing
  → Maintain current limits if no legitimate complaints

IF 1-10 violations/day:
  → Limits are appropriate
  → Continue monitoring

IF 11-50 violations/day:
  → Limits may be too strict
  → Increase by 25% and re-test

IF > 50 violations/day:
  → Possible attack or legitimate surge
  → Investigate endpoint patterns
  → May need per-endpoint adjustment
```

**Adjustment Examples:**
```bash
# Increase public limit (if too strict)
railway variables set RATE_LIMIT_PUBLIC="30/minute" -s boss-workflow

# Increase authenticated limit (if too strict)
railway variables set RATE_LIMIT_AUTHENTICATED="150/minute" -s boss-workflow

# Set per-endpoint limits (future)
# Will require code changes in slowapi_limiter.py
```

**Verification After Adjustment:**
```bash
# Test new limits immediately
for i in {1..150}; do
  curl -s -H "X-API-Key: test-key" \
    https://boss-workflow-production.up.railway.app/api/db/tasks
done
# Should see rate limit around request 100
```

---

## Phase 3: Remove Old Middleware (Week 3)

**Timeline:** Week of February 8, 2026

**Only if slowapi performs well after adjustments:**

### Option A: Keep Both (Recommended)
- Maintain feature flag indefinitely
- Allows quick switching if issues arise
- Minimal code overhead

### Option B: Remove Custom Middleware
If slowapi has proven robust:
```bash
# Delete old middleware (after backing up)
rm src/middleware/rate_limit.py

# Update main.py to remove fallback
# → Remove else block in rate limiting setup

# Clean up imports
# → Remove RateLimitMiddleware import
```

**Only proceed with Option B if:**
- Week 1-2 showed zero Redis errors
- Zero user complaints about rate limiting
- Metrics consistently clean
- Full test suite passing

---

## Rollback Plan

**Instant Rollback (if issues occur):**
```bash
# Disable slowapi with single command
railway variables set USE_SLOWAPI_RATE_LIMITING=false -s boss-workflow

# App will auto-switch to custom middleware on next request
# No downtime, no code deployment required
```

**No Code Changes Needed** - Feature flag controls behavior entirely.

---

## Monitoring & Alerting

### Key Metrics to Track

**1. Rate Limit Violations**
```python
# From Prometheus metrics
rate_limit_violations_total{endpoint="/api/db/tasks", limiter="slowapi"}
```

**2. Response Time Impact**
```
# Compare before/after
GET /api/db/tasks response time:
  - Before slowapi: ~50ms (P95)
  - Target impact: < 55ms (P95)
```

**3. Redis Backend Health**
```
# Ensure Redis doesn't become bottleneck
redis_connection_errors_total
redis_response_time_ms
redis_memory_usage_percent
```

### Alert Thresholds

| Metric | Alert Level | Action |
|--------|------------|--------|
| Violations/hour | > 100 | Investigate endpoint |
| Redis errors/hour | > 10 | Check Redis health, consider rollback |
| Response time impact | > 10ms | Profile middleware, check Redis |
| User complaints | 1+ | Analyze pattern, consider adjustment |

---

## Production Validation Checklist

### Pre-Deployment ✅
- [x] Slowapi library installed and tested
- [x] Redis backend accessible
- [x] Feature flag default: `false`
- [x] Rate limit settings configurable
- [x] Monitoring metrics defined
- [x] Rollback procedure documented

### Immediate Post-Deployment (Hour 1)
- [ ] Health check passes: `/health` returns 200
- [ ] Rate limit headers present in responses
- [ ] Metrics endpoint available: `/metrics`
- [ ] Sample requests tracked in Prometheus
- [ ] No error logs related to rate limiting

### First 24 Hours
- [ ] Monitor logs: `railway logs | grep -i rate`
- [ ] Check metrics dashboard
- [ ] Verify no user complaints in Telegram/Discord
- [ ] Test rate limiting manually (100 rapid requests should trigger limit)

### First Week
- [ ] Daily metric review
- [ ] No unexpected violations
- [ ] User feedback collected
- [ ] Response time baselines established

---

## Weekly Review Schedule

**Every Friday (9 AM Thailand Time):**
```bash
# Generate rate limit report
python scripts/rate_limit_report.py

# Review metrics
curl https://boss-workflow-production.up.railway.app/metrics | grep rate_limit

# Check logs for errors
railway logs -s boss-workflow | grep -i "error\|warn" | tail -20
```

---

## Decision Log

| Date | Decision | Reason | Action |
|------|----------|--------|--------|
| 2026-01-25 | Enable slowapi | Production hardening required | Deploy with feature flag |
| 2026-02-01 | ? | TBD | TBD |
| 2026-02-08 | ? | TBD | TBD |

---

## Troubleshooting Guide

### Issue: High Violation Rate (> 100/day)

**Diagnosis:**
```bash
# Check which endpoints are rate limited
railway logs -s boss-workflow | grep "429\|rate limit"

# Check if specific IPs are being hit hard
# Check if specific endpoints are legitimate bottlenecks
```

**Solutions:**
1. Increase global limits temporarily
2. Create per-endpoint limits (code change)
3. Investigate if legitimate API spike (new feature, testing)
4. Check for bot attacks (suspicious patterns)

### Issue: Redis Connection Errors

**Diagnosis:**
```bash
# Check Redis health
redis-cli -u $REDIS_URL ping

# Check connection pool usage
railway logs -s boss-workflow | grep -i redis
```

**Solutions:**
1. Verify Redis URL is correct
2. Check network connectivity
3. Increase Redis connection pool size
4. Rollback to custom middleware if persistent

### Issue: False Positives (Legitimate Users Blocked)

**User Reports:**
- "I'm getting 429 even though I'm not hammering the API"
- "My app suddenly started failing"

**Diagnosis:**
```bash
# Check if legitimate endpoint was incorrectly limited
# Review user's access pattern
# Check for shared IP addresses (NAT/proxy)
```

**Solutions:**
1. Whitelist specific API keys if needed
2. Implement token bucket strategy (more lenient)
3. Add exemption list for high-volume legitimate clients
4. Adjust limits upward if threshold too aggressive

---

## Contact & Escalation

**Rate Limiting Issues:**
- Check: This document's troubleshooting section
- Investigate: Railway logs and Prometheus metrics
- Escalate: If > 100 violations/day or > 5 user complaints
- Fallback: Disable with `USE_SLOWAPI_RATE_LIMITING=false`

**Critical Issues (Immediate Rollback):**
- Redis backend down for > 5 minutes
- Rate limiting affecting > 10% of legitimate requests
- P95 response time increase > 20ms
- Cascading failures in dependent systems

---

*Last Updated: 2026-01-25*
*Next Review: 2026-02-01*
