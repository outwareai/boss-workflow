"""
Tests for src/monitoring/alerts.py

Tests alerting system including alert severity levels, alert manager,
and integration with Slack/Discord webhooks.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.monitoring.alerts import (
    AlertSeverity,
    AlertManager,
)


class TestAlertSeverity:
    """Tests for AlertSeverity enum."""

    def test_severity_levels_exist(self):
        """Test that all severity levels are defined."""
        assert AlertSeverity.CRITICAL == "critical"
        assert AlertSeverity.WARNING == "warning"
        assert AlertSeverity.INFO == "info"

    def test_severity_is_string_enum(self):
        """Test that severity inherits from str."""
        assert isinstance(AlertSeverity.CRITICAL, str)
        assert isinstance(AlertSeverity.WARNING, str)


class TestAlertManager:
    """Tests for AlertManager class."""

    @patch('src.monitoring.alerts.settings')
    def test_init_sets_webhooks(self, mock_settings):
        """Test that init sets webhook URLs from settings."""
        mock_settings.slack_alert_webhook = "https://slack.example.com"
        mock_settings.discord_alert_webhook = "https://discord.example.com"
        mock_settings.alert_error_rate_threshold = 0.05
        mock_settings.alert_response_time_threshold = 1000

        manager = AlertManager()

        assert manager.slack_webhook == "https://slack.example.com"
        assert manager.discord_webhook == "https://discord.example.com"

    @patch('src.monitoring.alerts.settings')
    def test_alert_thresholds_configured(self, mock_settings):
        """Test that alert thresholds are properly configured."""
        mock_settings.slack_alert_webhook = None
        mock_settings.discord_alert_webhook = None
        mock_settings.alert_error_rate_threshold = 0.05
        mock_settings.alert_response_time_threshold = 1000

        manager = AlertManager()

        assert "error_rate" in manager.alert_threshold
        assert "response_time_p95" in manager.alert_threshold
        assert "db_pool_usage" in manager.alert_threshold
        assert "cache_hit_rate" in manager.alert_threshold


@pytest.mark.asyncio
class TestAlertManagerSendAlert:
    """Tests for AlertManager.send_alert method."""

    @patch('src.monitoring.alerts.settings')
    async def test_send_alert_disabled_skips_sending(self, mock_settings):
        """Test that alerts are skipped when disabled."""
        mock_settings.enable_alerting = False
        mock_settings.slack_alert_webhook = "https://slack.example.com"
        mock_settings.discord_alert_webhook = None
        mock_settings.alert_error_rate_threshold = 0.05
        mock_settings.alert_response_time_threshold = 1000

        manager = AlertManager()
        manager._send_to_slack = AsyncMock()

        await manager.send_alert(
            title="Test Alert",
            message="Test message",
            severity=AlertSeverity.INFO
        )

        manager._send_to_slack.assert_not_called()

    @patch('src.monitoring.alerts.get_settings')
    async def test_send_alert_to_slack_when_configured(self, mock_settings):
        """Test that alert is sent to Slack when webhook is configured."""
        mock_settings.return_value.enable_alerting = True
        mock_settings.return_value.slack_alert_webhook = "https://slack.example.com"
        mock_settings.return_value.discord_alert_webhook = None
        mock_settings.return_value.alert_error_rate_threshold = 0.05
        mock_settings.return_value.alert_response_time_threshold = 1000

        manager = AlertManager()
        manager._send_to_slack = AsyncMock()

        await manager.send_alert(
            title="Test Alert",
            message="Test message",
            severity=AlertSeverity.WARNING
        )

        manager._send_to_slack.assert_called_once()

    @patch('src.monitoring.alerts.get_settings')
    async def test_send_alert_to_discord_when_configured(self, mock_settings):
        """Test that alert is sent to Discord when webhook is configured."""
        mock_settings.return_value.enable_alerting = True
        mock_settings.return_value.slack_alert_webhook = None
        mock_settings.return_value.discord_alert_webhook = "https://discord.example.com"
        mock_settings.return_value.alert_error_rate_threshold = 0.05
        mock_settings.return_value.alert_response_time_threshold = 1000

        manager = AlertManager()
        manager._send_to_discord = AsyncMock()

        await manager.send_alert(
            title="Test Alert",
            message="Test message",
            severity=AlertSeverity.CRITICAL
        )

        manager._send_to_discord.assert_called_once()

    @patch('src.monitoring.alerts.get_settings')
    async def test_send_alert_to_both_channels(self, mock_settings):
        """Test that alert is sent to both Slack and Discord if both configured."""
        mock_settings.return_value.enable_alerting = True
        mock_settings.return_value.slack_alert_webhook = "https://slack.example.com"
        mock_settings.return_value.discord_alert_webhook = "https://discord.example.com"
        mock_settings.return_value.alert_error_rate_threshold = 0.05
        mock_settings.return_value.alert_response_time_threshold = 1000

        manager = AlertManager()
        manager._send_to_slack = AsyncMock()
        manager._send_to_discord = AsyncMock()

        await manager.send_alert(
            title="Test Alert",
            message="Test message",
            severity=AlertSeverity.INFO
        )

        manager._send_to_slack.assert_called_once()
        manager._send_to_discord.assert_called_once()

    @patch('src.monitoring.alerts.get_settings')
    async def test_send_alert_includes_metrics(self, mock_settings):
        """Test that alerts can include metrics."""
        mock_settings.return_value.enable_alerting = True
        mock_settings.return_value.slack_alert_webhook = "https://slack.example.com"
        mock_settings.return_value.discord_alert_webhook = None
        mock_settings.return_value.alert_error_rate_threshold = 0.05
        mock_settings.return_value.alert_response_time_threshold = 1000

        manager = AlertManager()
        manager._send_to_slack = AsyncMock()

        metrics = {"error_rate": 0.15, "response_time": 2500}

        await manager.send_alert(
            title="High Error Rate",
            message="Error rate exceeded threshold",
            severity=AlertSeverity.CRITICAL,
            metrics=metrics
        )

        # Check that metrics were passed
        call_args = manager._send_to_slack.call_args[0][0]
        assert "metrics" in call_args
        assert call_args["metrics"] == metrics

    @patch('src.monitoring.alerts.get_settings')
    async def test_send_alert_handles_slack_failure(self, mock_settings):
        """Test that Slack failure doesn't crash the alert system."""
        mock_settings.return_value.enable_alerting = True
        mock_settings.return_value.slack_alert_webhook = "https://slack.example.com"
        mock_settings.return_value.discord_alert_webhook = "https://discord.example.com"
        mock_settings.return_value.alert_error_rate_threshold = 0.05
        mock_settings.return_value.alert_response_time_threshold = 1000

        manager = AlertManager()
        manager._send_to_slack = AsyncMock(side_effect=Exception("Slack error"))
        manager._send_to_discord = AsyncMock()

        # Should not raise exception
        await manager.send_alert(
            title="Test",
            message="Message",
            severity=AlertSeverity.INFO
        )

        # Discord should still be called
        manager._send_to_discord.assert_called_once()

    @patch('src.monitoring.alerts.get_settings')
    async def test_send_alert_handles_discord_failure(self, mock_settings):
        """Test that Discord failure doesn't crash the alert system."""
        mock_settings.return_value.enable_alerting = True
        mock_settings.return_value.slack_alert_webhook = "https://slack.example.com"
        mock_settings.return_value.discord_alert_webhook = "https://discord.example.com"
        mock_settings.return_value.alert_error_rate_threshold = 0.05
        mock_settings.return_value.alert_response_time_threshold = 1000

        manager = AlertManager()
        manager._send_to_slack = AsyncMock()
        manager._send_to_discord = AsyncMock(side_effect=Exception("Discord error"))

        # Should not raise exception
        await manager.send_alert(
            title="Test",
            message="Message",
            severity=AlertSeverity.WARNING
        )

        # Slack should still be called
        manager._send_to_slack.assert_called_once()

    @patch('src.monitoring.alerts.get_settings')
    async def test_send_alert_formats_title_with_severity(self, mock_settings):
        """Test that alert title includes severity level."""
        mock_settings.return_value.enable_alerting = True
        mock_settings.return_value.slack_alert_webhook = "https://slack.example.com"
        mock_settings.return_value.discord_alert_webhook = None
        mock_settings.return_value.alert_error_rate_threshold = 0.05
        mock_settings.return_value.alert_response_time_threshold = 1000

        manager = AlertManager()
        manager._send_to_slack = AsyncMock()

        await manager.send_alert(
            title="System Error",
            message="Something went wrong",
            severity=AlertSeverity.CRITICAL
        )

        call_args = manager._send_to_slack.call_args[0][0]
        assert "[CRITICAL]" in call_args["title"]
        assert "System Error" in call_args["title"]

    @patch('src.monitoring.alerts.get_settings')
    async def test_send_alert_includes_timestamp(self, mock_settings):
        """Test that alerts include a timestamp."""
        mock_settings.return_value.enable_alerting = True
        mock_settings.return_value.slack_alert_webhook = "https://slack.example.com"
        mock_settings.return_value.discord_alert_webhook = None
        mock_settings.return_value.alert_error_rate_threshold = 0.05
        mock_settings.return_value.alert_response_time_threshold = 1000

        manager = AlertManager()
        manager._send_to_slack = AsyncMock()

        await manager.send_alert(
            title="Test",
            message="Message",
            severity=AlertSeverity.INFO
        )

        call_args = manager._send_to_slack.call_args[0][0]
        assert "timestamp" in call_args
        assert call_args["timestamp"] is not None

    @patch('src.monitoring.alerts.get_settings')
    async def test_send_alert_different_colors_for_severities(self, mock_settings):
        """Test that different severities use different colors."""
        mock_settings.return_value.enable_alerting = True
        mock_settings.return_value.slack_alert_webhook = "https://slack.example.com"
        mock_settings.return_value.discord_alert_webhook = None
        mock_settings.return_value.alert_error_rate_threshold = 0.05
        mock_settings.return_value.alert_response_time_threshold = 1000

        manager = AlertManager()
        manager._send_to_slack = AsyncMock()

        # Send critical alert
        await manager.send_alert("Test", "Message", AlertSeverity.CRITICAL)
        critical_color = manager._send_to_slack.call_args[0][1]

        # Send warning alert
        await manager.send_alert("Test", "Message", AlertSeverity.WARNING)
        warning_color = manager._send_to_slack.call_args[0][1]

        # Send info alert
        await manager.send_alert("Test", "Message", AlertSeverity.INFO)
        info_color = manager._send_to_slack.call_args[0][1]

        # Colors should be different
        assert critical_color != warning_color
        assert warning_color != info_color
        assert critical_color != info_color
