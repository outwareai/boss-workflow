# Boss Workflow Monitoring Setup

## Overview

This monitoring stack provides comprehensive observability for the Boss Workflow application using Prometheus for metrics collection and Grafana for visualization.

## Components

- **Prometheus**: Metrics collection and storage
- **Grafana**: Metrics visualization and dashboards
- **AlertManager**: Alert routing and notification

## Quick Start

### 1. Start Monitoring Stack

```bash
cd boss-workflow
docker-compose -f docker-compose.monitoring.yml up -d
```

### 2. Access Dashboards

- **Grafana**: http://localhost:3000 (admin/admin)
- **Prometheus**: http://localhost:9090
- **AlertManager**: http://localhost:9093

### 3. Import Dashboard

1. Open Grafana at http://localhost:3000
2. Login with admin/admin
3. Go to Dashboards → Import
4. Upload `grafana/boss-workflow-dashboard.json`
5. Select Prometheus as data source

## Metrics Exposed

### HTTP Metrics
- `http_requests_total`: Total HTTP requests (labels: method, endpoint, status)
- `http_request_duration_seconds`: Request duration histogram

### Task Metrics
- `tasks_created_total`: Total tasks created (labels: assignee, priority)
- `tasks_completed_total`: Total tasks completed (labels: assignee)
- `tasks_by_status`: Current task count by status

### Database Metrics
- `db_queries_total`: Total database queries (labels: operation)
- `db_query_duration_seconds`: Query duration histogram
- `db_pool_connections`: Connection pool status (labels: state)

### AI Metrics
- `ai_requests_total`: Total AI API requests (labels: operation, status)
- `ai_request_duration_seconds`: AI request duration histogram

### Cache Metrics
- `cache_operations_total`: Cache operations (labels: operation, result)

### Discord Metrics
- `discord_messages_sent_total`: Discord messages sent (labels: channel, status)

### Error Metrics
- `errors_total`: Total errors (labels: type, severity)

## Configuration

### For Local Development

The default `prometheus.yml` is configured for local development using `host.docker.internal:8000`.

### For Railway/Production

Update `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: 'boss-workflow'
    static_configs:
      - targets:
          - 'boss-workflow-production.up.railway.app:443'
    metrics_path: '/metrics'
    scheme: https
    tls_config:
      insecure_skip_verify: true
```

### For Discord Alerts

Set environment variable in `alertmanager.yml`:

```bash
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."
```

Or replace `${DISCORD_WEBHOOK_URL}` directly in the config.

## Alerts

Alerts are defined in `alerts.yml`:

- **HighErrorRate**: >5% HTTP errors for 5 minutes
- **SlowAPIResponses**: p95 response time >2s
- **DatabasePoolExhaustion**: >5 overflow connections
- **HighDatabaseLatency**: p95 query time >1s
- **LowCacheHitRate**: <50% cache hit rate
- **AIRequestFailures**: >10% AI request failures
- **ApplicationDown**: Application unreachable for >1 minute

## Viewing Metrics

### Via Prometheus

1. Open http://localhost:9090
2. Go to Graph tab
3. Enter a PromQL query, e.g.:
   ```
   rate(http_requests_total[5m])
   ```

### Via Grafana

1. Open http://localhost:3000
2. Navigate to imported "Boss Workflow Monitoring" dashboard
3. View pre-configured panels with key metrics

### Via API

```bash
# Get all metrics
curl http://localhost:8000/metrics

# Get specific metric
curl http://localhost:8000/metrics | grep tasks_created_total
```

## Troubleshooting

### Prometheus can't reach application

**Problem**: Prometheus shows target as "down"

**Solution**:
- Check if application is running: `curl http://localhost:8000/health`
- Verify metrics endpoint: `curl http://localhost:8000/metrics`
- For Docker: Use `host.docker.internal` instead of `localhost`
- Check firewall rules

### No data in Grafana

**Problem**: Grafana panels show "No Data"

**Solution**:
- Verify Prometheus is scraping: http://localhost:9090/targets
- Check data source connection in Grafana
- Ensure time range is correct (last 15 minutes)
- Verify metrics exist: http://localhost:9090/graph

### Alerts not firing

**Problem**: Expected alerts not appearing

**Solution**:
- Check alert rules: http://localhost:9090/alerts
- Verify AlertManager is running: http://localhost:9093
- Check Discord webhook URL is correct
- Review AlertManager logs: `docker logs boss-workflow-alertmanager`

## Production Deployment

### Option 1: Railway (Recommended)

Add monitoring as a separate service in Railway:

1. Create new service for Prometheus
2. Add environment variables:
   ```
   PROMETHEUS_CONFIG_URL=https://raw.githubusercontent.com/.../prometheus.yml
   ```
3. Deploy Grafana Cloud (free tier) or Railway-hosted Grafana

### Option 2: Docker Compose on VPS

1. Deploy monitoring stack alongside application
2. Use reverse proxy (Traefik/Nginx) for HTTPS
3. Configure authentication for Grafana/Prometheus

### Option 3: Managed Services

- Use Grafana Cloud (free tier: 10k metrics)
- Use Datadog/New Relic (paid)
- Use AWS CloudWatch (if on AWS)

## Best Practices

1. **Set Up Alerts**: Configure critical alerts for production
2. **Monitor Regularly**: Review dashboards weekly
3. **Retention**: Keep metrics for 30 days minimum
4. **Security**: Add authentication to Prometheus/Grafana in production
5. **Backup**: Export Grafana dashboards regularly

## Further Reading

- [Prometheus Documentation](https://prometheus.io/docs/)
- [Grafana Documentation](https://grafana.com/docs/)
- [PromQL Cheat Sheet](https://promlabs.com/promql-cheat-sheet/)
