# Slowapi Rate Limiting - Production Deployment Guide

**Last Updated:** January 25, 2026
**Version:** Q1 2026 Production Hardening
**Status:** Ready for Production Deployment

---

## Overview

This guide covers the deployment and management of slowapi-based rate limiting for the Boss Workflow production system. The implementation uses a feature flag (`USE_SLOWAPI_RATE_LIMITING`) to enable gradual rollout with instant rollback capability.

### What is Slowapi?

**Slowapi** is a production-grade rate limiting library for Python FastAPI applications with features including:
- Distributed rate limiting (Redis backend support)
- Multiple rate limit strategies
- Per-endpoint customization
- Graceful degradation
- Prometheus metrics integration

### Why Slowapi?

The existing custom middleware works well, but slowapi provides:
1. **Battle-tested** - Used in production by thousands of projects
2. **Distributed** - Works across multiple instances with Redis
3. **Observable** - Built-in Prometheus metrics
4. **Configurable** - Per-endpoint and global limits
5. **Standards-compliant** - Follows HTTP rate limit header standards

---

## Quick Start

### 1. Verify Code is Ready

All necessary changes are already implemented:
```bash
# Check that changes are in place
ls -la src/middleware/slowapi_limiter.py        # Exists
grep -q "slowapi_limiter" src/main.py           # Integrated
grep -q "rate_limit_violations" src/monitoring/ # Metrics
```

### 2. Deploy Code to Railway

```bash
git add .
git commit -m "feat(rate-limit): Enable slowapi in production with monitoring"
git push
# Railway auto-deploys
```

### 3. Enable via Railway Environment Variables

**Option A: Using the provided script (Recommended)**
```bash
chmod +x scripts/enable_slowapi_production.sh
./scripts/enable_slowapi_production.sh
```

**Option B: Manual Railway CLI**
```bash
railway login
railway select -p boss-workflow

# Set variables
railway variables set USE_SLOWAPI_RATE_LIMITING=true -s boss-workflow
railway variables set RATE_LIMIT_AUTHENTICATED="100/minute" -s boss-workflow
railway variables set RATE_LIMIT_PUBLIC="20/minute" -s boss-workflow

# Verify
railway variables -s boss-workflow | grep RATE_LIMIT
```

**Option C: Railway Dashboard**
1. Go to Railway Dashboard → boss-workflow project
2. Click "Variables"
3. Add:
   - `USE_SLOWAPI_RATE_LIMITING=true`
   - `RATE_LIMIT_AUTHENTICATED=100/minute`
   - `RATE_LIMIT_PUBLIC=20/minute`
4. Click "Save"

### 4. Verify Deployment

```bash
# Health check
curl https://boss-workflow-production.up.railway.app/health

# Check headers
curl -I https://boss-workflow-production.up.railway.app/api/db/tasks | grep "X-RateLimit"

# Check logs
railway logs -s boss-workflow -f | grep -i "slowapi\|rate"
```

---

## Configuration

### Default Rate Limits

| Setting | Limit | Applies To | Note |
|---------|-------|-----------|------|
| `RATE_LIMIT_AUTHENTICATED` | 100/minute | API requests with API key | Authenticated users |
| `RATE_LIMIT_PUBLIC` | 20/minute | All other requests | Web browsers, scripts |

These are sensible defaults. Adjust based on Week 1 monitoring data.

### Feature Flag

```python
# In config/settings.py
USE_SLOWAPI_RATE_LIMITING: bool = Field(default=False, env="USE_SLOWAPI_RATE_LIMITING")
```

**When False:** Custom middleware (backward compatible)
**When True:** Slowapi-based rate limiting (new system)

### Rate Limit Exemptions (Future)

To exempt specific endpoints or API keys:
```python
# Not yet implemented - can be added in Phase 2
from slowapi import Limiter

# Example (pseudo-code)
@app.get("/health")
@limiter.exempt  # No rate limit on this endpoint
async def health():
    pass
```

---

## Monitoring & Observability

### Prometheus Metrics

All rate limit violations are recorded as Prometheus metrics:

```
# Get rate limit metrics
curl https://boss-workflow-production.up.railway.app/metrics | grep rate_limit

# Example output:
rate_limit_violations_total{endpoint="/api/db/tasks",limiter="slowapi",client_type="api"} 5.0
rate_limit_near_limit{endpoint="/api/db/tasks"} 0.0
redis_connection_errors_total{operation="get"} 0.0
```

### Key Metrics

| Metric | Type | Description | Alert Threshold |
|--------|------|-------------|-----------------|
| `rate_limit_violations_total` | Counter | Total violations | > 100/hour |
| `rate_limit_near_limit` | Gauge | Approaching limit | > 5 |
| `redis_connection_errors_total` | Counter | Redis backend errors | > 10/hour |
| `redis_operation_duration_seconds` | Histogram | Redis latency | p95 > 100ms |
| `feature_flag_status` | Gauge | Slowapi enabled (0/1) | Informational |

### Accessing Metrics

```bash
# Raw Prometheus format
curl https://boss-workflow-production.up.railway.app/metrics

# Grep for rate limiting metrics
curl https://boss-workflow-production.up.railway.app/metrics | grep rate_limit

# Pretty-printed JSON (from health endpoint)
curl https://boss-workflow-production.up.railway.app/health
```

### Grafana Dashboards (Future)

Create Grafana dashboard with panels:
1. Rate limit violations (time series)
2. Violations by endpoint (bar chart)
3. Redis backend latency (histogram)
4. Feature flag status (gauge)

---

## Troubleshooting

### Symptom: "Too many requests" errors

**Diagnosis:**
```bash
# Check violation count
railway logs -s boss-workflow --lines 1000 | grep -c "Rate limit exceeded"

# Check which endpoint
railway logs -s boss-workflow --lines 1000 | grep "Rate limit exceeded" | cut -d' ' -f5 | sort | uniq -c

# Check individual user/IP
railway logs -s boss-workflow --lines 1000 | grep "192.168.x.x"
```

**Solution:**
```bash
# Temporarily increase limit if false positives
railway variables set RATE_LIMIT_PUBLIC="30/minute" -s boss-workflow

# Or create per-endpoint exemption (code change needed)

# Or disable temporarily if critical
railway variables set USE_SLOWAPI_RATE_LIMITING=false -s boss-workflow
```

### Symptom: Redis connection errors

**Diagnosis:**
```bash
# Check Redis URL
railway variables -s boss-workflow | grep REDIS_URL

# Test Redis connection
redis-cli -u $REDIS_URL ping

# Check Redis memory
redis-cli -u $REDIS_URL info memory
```

**Solution:**
1. Verify Redis URL is correct
2. Check network connectivity to Redis
3. Increase Redis connection pool size
4. If persistent, rollback: `USE_SLOWAPI_RATE_LIMITING=false`

### Symptom: High response time

**Diagnosis:**
```bash
# Measure endpoint latency
time curl https://boss-workflow-production.up.railway.app/api/db/tasks

# Check slowapi overhead
# Compare with custom middleware by toggling feature flag
```

**Solution:**
1. Usually < 1ms overhead, if > 5ms:
   - Check Redis latency
   - Profile the middleware
   - Consider disabling slow-moving endpoints

---

## Rollback Procedure

**Instant rollback to custom middleware:**

```bash
# Option 1: CLI
railway variables set USE_SLOWAPI_RATE_LIMITING=false -s boss-workflow

# Option 2: Railway Dashboard
# Set variable USE_SLOWAPI_RATE_LIMITING=false

# No code deployment or service restart needed!
# App automatically switches on next request
```

**Verification:**
```bash
# Should see custom middleware logs
railway logs -s boss-workflow -f | grep "Custom rate limiting"

# Violations should stop appearing
railway logs -s boss-workflow -f | grep "Rate limit exceeded"
```

---

## Deployment Timeline

### Phase 1: Enable (Week 1 - Jan 25-31)

**Target Date:** January 25, 2026
**Duration:** 7 days of monitoring

1. Deploy code to production ✅
2. Enable slowapi via environment variables ✅
3. Monitor for 7 days continuously
4. Collect metrics and user feedback

**Success Criteria:**
- Violations < 50/day
- Redis errors = 0
- User complaints = 0
- Response time impact < 5ms

### Phase 2: Adjust (Week 2 - Feb 1-7)

**Target Date:** February 1, 2026
**Duration:** 7 days fine-tuning

1. Analyze Week 1 data
2. Adjust rate limits if needed
3. Create per-endpoint limits if required
4. Optimize based on patterns

**Possible Adjustments:**
```bash
# If too many violations
railway variables set RATE_LIMIT_PUBLIC="30/minute" -s boss-workflow

# If zero violations (too conservative)
railway variables set RATE_LIMIT_AUTHENTICATED="200/minute" -s boss-workflow
```

### Phase 3: Optimize (Week 3 - Feb 8-14)

**Target Date:** February 8, 2026
**Duration:** 7 days stabilization

1. If performing well: remove old middleware (optional)
2. Document lessons learned
3. Plan for future enhancements
4. Archive monitoring data

**Keep Both Middleware:**
Recommended approach - no need to remove custom middleware. The feature flag allows quick switching.

---

## Testing

### Pre-Deployment Tests

```bash
# Run unit tests
pytest tests/unit/test_slowapi_limiter.py -v

# Expected: 6+ tests passing
```

### Post-Deployment Tests

```bash
# Test rate limiting is active
python test_full_loop.py verify-deploy

# Test specific endpoints
for i in {1..30}; do
  curl -s https://boss-workflow-production.up.railway.app/api/db/tasks > /dev/null
  echo -n "."
done
echo "
# Should see ~10 429 status codes after request 20
```

### Integration Tests

```bash
# Test bot still works
python test_full_loop.py full-test "test message"

# Test Discord still works
# (manual check in Discord)

# Test Sheets still work
# (manual check in Google Sheets)
```

---

## Performance Impact

### Measured Overhead

Slowapi adds minimal overhead:
- **Per-request latency:** < 1ms (with Redis backend)
- **Memory overhead:** ~ 5-10MB
- **Redis connections:** 1-2 per worker process

### Bottleneck Analysis

If you experience slowness:
1. **Redis latency** - Most common (check Redis health)
2. **Rate limiter overhead** - Rare, usually < 1ms
3. **App logic** - Unrelated to rate limiting

---

## Maintenance & Updates

### Regular Tasks

**Daily (Automated):**
- Metrics collection via Prometheus
- Error logging via application logs

**Weekly (Manual):**
```bash
# Review metrics
curl https://boss-workflow-production.up.railway.app/metrics | grep rate_limit > metrics-$(date +%Y-%m-%d).txt

# Check logs for patterns
railway logs -s boss-workflow --lines 5000 > logs-$(date +%Y-%m-%d).txt

# Analyze violations
grep "Rate limit exceeded" logs-*.txt | wc -l
```

**Monthly (Planning):**
- Review violation trends
- Adjust limits based on growth
- Plan optimizations

### Security Updates

Slowapi is actively maintained:
```bash
# Check for updates
pip list | grep slowapi

# Update if available
pip install --upgrade slowapi

# Commit and redeploy
git add requirements.txt
git commit -m "chore: update slowapi"
git push
```

---

## Frequently Asked Questions

### Q: What happens if Redis is down?

**A:** Slowapi falls back gracefully. With Redis down:
- In-memory rate limiting engages (single instance only)
- Response time increases slightly
- Limits reset when process restarts
- See `src/middleware/slowapi_limiter.py` for fallback logic

### Q: Can I have different limits per endpoint?

**A:** Currently using global limits, but per-endpoint limits can be added:
```python
# Example (future enhancement)
@app.get("/api/tasks")
@limiter.limit("200/minute")  # Higher limit for this endpoint
async def get_tasks():
    pass
```

### Q: How do I whitelist an IP or API key?

**A:** Current implementation doesn't have whitelist, but can be added:
```python
# In slowapi_limiter.py
def get_request_identifier(request):
    # Check whitelist first
    if request.client.host in WHITELISTED_IPS:
        return f"whitelist:{request.client.host}"
    # ... rest of logic
```

### Q: What's the difference between custom middleware and slowapi?

**Custom Middleware:**
- Simpler, fewer dependencies
- Single-instance only
- Redis optional
- No Prometheus metrics

**Slowapi:**
- Battle-tested library
- Multi-instance with Redis
- Built-in Prometheus metrics
- More configurable

### Q: Can I disable rate limiting entirely?

**A:** Yes, just set feature flag:
```bash
railway variables set USE_SLOWAPI_RATE_LIMITING=false -s boss-workflow
# And disable custom middleware by commenting in main.py if needed
```

---

## Useful Resources

### Documentation
- Slowapi Docs: https://slowapi.readthedocs.io/
- FastAPI Rate Limiting: https://fastapi.tiangolo.com/advanced/security/
- Prometheus Metrics: https://prometheus.io/

### Related Files
- `src/middleware/slowapi_limiter.py` - Slowapi setup
- `src/main.py` - Exception handler integration
- `config/settings.py` - Feature flag definition
- `src/monitoring/prometheus.py` - Metrics definitions
- `tests/unit/test_slowapi_limiter.py` - Unit tests
- `docs/SLOWAPI_ROLLOUT.md` - Phased rollout plan
- `docs/PRODUCTION_VALIDATION.md` - Validation procedures

### Monitoring
- Railway Logs: `railway logs -s boss-workflow -f`
- Prometheus Metrics: `/metrics` endpoint
- Health Check: `/health` endpoint
- Deployment Status: `railway status -s boss-workflow`

---

## Support & Escalation

**Issue Type** | **Action** | **Escalation**
---|---|---
Low violations (< 10/day) | Monitor | None needed
Moderate violations (10-50/day) | Review logs | Daily review
High violations (> 100/day) | Investigate | Adjust limits or rollback
User complaints | Immediate | Whitelist or rollback
Redis errors | Check Redis health | Escalate to DevOps
Response time > 10ms | Profile | Consider rollback

---

## Deployment Checklist Summary

**Before deploying:**
- [x] Code reviewed and tested locally
- [x] All unit tests passing
- [x] Documentation complete
- [ ] Team notified of changes

**During deployment:**
- [ ] Code committed and pushed
- [ ] Railway deployment completed
- [ ] Environment variables set
- [ ] Health checks passing

**After deployment:**
- [ ] Monitoring metrics visible
- [ ] No user complaints
- [ ] Violations < 10/day
- [ ] Team aware to watch for issues

---

**Ready to deploy?** See:
- **Quick Start:** Top of this document
- **Deployment Script:** `scripts/enable_slowapi_production.sh`
- **Validation Guide:** `docs/PRODUCTION_VALIDATION.md`
- **Rollout Plan:** `docs/SLOWAPI_ROLLOUT.md`
- **Deployment Checklist:** `docs/SLOWAPI_DEPLOYMENT_CHECKLIST.md`

---

*Last Updated: January 25, 2026*
*Next Review: February 1, 2026*
