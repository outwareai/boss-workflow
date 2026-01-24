# Load Testing Guide

## Overview

This suite validates Boss Workflow's ability to handle **1,000 requests/minute** under production load conditions.

## Quick Start

### Install Dependencies

```bash
pip install locust
```

### Run Quick Benchmark

```bash
# Local server
python tests/load/benchmark.py

# Remote server
python tests/load/benchmark.py https://boss-workflow-production.up.railway.app
```

### Run Single Scenario

```bash
# Light load test (100 users)
python tests/load/scenarios.py light

# Medium load (500 users)
python tests/load/scenarios.py medium

# Heavy load (1000 users) - TARGET CAPACITY
python tests/load/scenarios.py heavy

# Spike test (2000 users)
python tests/load/scenarios.py spike
```

### Run Full Test Suite

**Linux/Mac:**
```bash
bash scripts/run_load_tests.sh
```

**Windows:**
```cmd
scripts\run_load_tests.bat
```

## Test Scenarios

### 1. Light Load
- **Users:** 100
- **Spawn Rate:** 10/sec
- **Duration:** 5 minutes
- **Purpose:** Warmup and basic functionality validation

### 2. Medium Load
- **Users:** 500
- **Spawn Rate:** 50/sec
- **Duration:** 10 minutes
- **Purpose:** Sustained moderate traffic testing

### 3. Heavy Load
- **Users:** 1000
- **Spawn Rate:** 100/sec
- **Duration:** 15 minutes
- **Purpose:** **Target capacity validation (1,000 req/min)**

### 4. Spike Test
- **Users:** 2000
- **Spawn Rate:** 200/sec
- **Duration:** 5 minutes
- **Purpose:** Sudden traffic spike behavior

## User Behavior Patterns

### BossWorkflowUser (Normal User)
- **List tasks** (40% - weight 10)
- **Get task by status** (20% - weight 5)
- **Get specific task** (16% - weight 4)
- **Create task** (12% - weight 3)
- **Update task status** (8% - weight 2)
- **Get statistics** (4% - weight 1)
- **Health check** (4% - weight 1)

### AdminUser (Admin User)
- **Get pool status** (50% - weight 1)
- **Get cache stats** (50% - weight 1)

## Success Criteria

| Metric | Target | Critical |
|--------|--------|----------|
| P95 Response Time | < 500ms | < 1000ms |
| P99 Response Time | < 1000ms | < 2000ms |
| Error Rate (Normal) | 0% | < 1% |
| Error Rate (Spike) | < 1% | < 5% |
| Throughput | 1,000 req/min | 800 req/min |
| Database Pool | No overflow | - |
| Cache Hit Rate | > 70% | > 50% |

## Interpreting Results

### HTML Reports

After each test, an HTML report is generated in `tests/load/reports/`:
- `report_100users.html` - Light load results
- `report_500users.html` - Medium load results
- `report_1000users.html` - Heavy load results
- `report_2000users.html` - Spike test results

Open in a browser to view:
- Request count and failure rate
- Response time charts (min/avg/max/P95/P99)
- Requests per second over time
- Individual endpoint performance

### CSV Stats

CSV files are also generated for programmatic analysis:
- `stats_100users_stats.csv` - Request statistics
- `stats_100users_stats_history.csv` - Historical data
- `stats_100users_failures.csv` - Failure details

### Benchmark Output

The benchmark script provides quick performance metrics:

```
1. List Tasks Endpoint
   Concurrent Requests: 50
   Mean: 245.32ms
   P95: 487.21ms
   P99: 823.45ms
   Failures: 0

Success Criteria:
  P95 < 500ms: ✓
  P99 < 1000ms: ✓
```

## Testing Against Production

### Railway Deployment

```bash
# Set production URL
export LOAD_TEST_HOST=https://boss-workflow-production.up.railway.app

# Run benchmarks
python tests/load/benchmark.py $LOAD_TEST_HOST

# Run specific scenario
python tests/load/scenarios.py heavy
```

**WARNING:** Be careful when load testing production:
- Coordinate with the team
- Run during low-traffic periods
- Monitor database and cache resources
- Have rollback plan ready

### Local Development

```bash
# Start server
python -m src.main

# In another terminal, run tests
python tests/load/benchmark.py http://localhost:8000
```

## Troubleshooting

### High Response Times

**Symptoms:** P95 > 1000ms, P99 > 2000ms

**Potential Causes:**
- Database connection pool exhausted
- Slow queries without indexes
- Blocking I/O operations
- Insufficient server resources

**Solutions:**
- Check `GET /api/admin/pool-status` for connection pool stats
- Review slow query logs
- Optimize with async operations
- Scale up EC2 instance

### High Failure Rate

**Symptoms:** Error rate > 5%

**Potential Causes:**
- Rate limiting triggered
- Database connection timeouts
- Memory exhaustion
- Network issues

**Solutions:**
- Check `railway logs` for errors
- Adjust rate limits in `config/settings.py`
- Monitor memory usage
- Verify network connectivity

### Database Pool Overflow

**Symptoms:** "Too many connections" errors

**Solutions:**
- Increase `pool_size` in database config
- Enable connection pooling in Railway
- Add connection timeout handling
- Implement connection recycling

### Cache Misses

**Symptoms:** Cache hit rate < 50%

**Solutions:**
- Review cache TTL settings
- Increase Redis memory allocation
- Optimize cache key patterns
- Pre-warm cache for common queries

## Advanced Usage

### Custom Locust UI

Run with web UI instead of headless:

```bash
locust -f tests/load/locustfile.py --host http://localhost:8000
# Open http://localhost:8089 in browser
```

### Distributed Load Testing

Run across multiple machines:

```bash
# Master
locust -f tests/load/locustfile.py --master

# Workers (on other machines)
locust -f tests/load/locustfile.py --worker --master-host=<master-ip>
```

### Custom Test Duration

```python
from tests.load.scenarios import LoadTestScenario

custom = LoadTestScenario(host="http://localhost:8000")
custom.run(users=750, spawn_rate=75, duration="30m")
```

## CI/CD Integration

Add to GitHub Actions:

```yaml
- name: Run Load Tests
  run: |
    pip install locust
    python tests/load/benchmark.py ${{ secrets.PRODUCTION_URL }}
```

## Monitoring During Tests

### Real-time Metrics

```bash
# In separate terminals:

# 1. Monitor logs
railway logs -s boss-workflow

# 2. Watch pool status
watch -n 1 'curl -s http://localhost:8000/api/admin/pool-status | jq'

# 3. Monitor cache
watch -n 1 'curl -s http://localhost:8000/api/admin/cache/stats | jq'
```

### Resource Monitoring

```bash
# Database connections
psql $DATABASE_URL -c "SELECT count(*) FROM pg_stat_activity;"

# Redis memory
redis-cli INFO memory

# CPU/Memory
htop
```

## Next Steps

After running load tests:

1. **Review reports** in `tests/load/reports/`
2. **Check success criteria** against targets
3. **Identify bottlenecks** from slowest endpoints
4. **Optimize code** based on findings
5. **Re-run tests** to validate improvements
6. **Document changes** in FEATURES.md

## References

- [Locust Documentation](https://docs.locust.io/)
- [Performance Testing Best Practices](https://docs.locust.io/en/stable/writing-a-locustfile.html)
- [Railway Metrics](https://docs.railway.app/guides/metrics)
