"""Tests for the task template system."""

import pytest
from src.models.templates import (
    apply_template,
    get_template,
    list_templates,
    validate_template_name,
    get_template_suggestions,
    format_template_help,
    TASK_TEMPLATES,
    TemplateType,
)


class TestTemplateAvailability:
    """Test that all templates are properly defined."""

    def test_all_templates_exist(self):
        """Test all expected templates are defined."""
        expected_templates = ["bug", "feature", "hotfix", "research", "meeting", "documentation", "review", "deployment"]
        for template_name in expected_templates:
            assert template_name in TASK_TEMPLATES, f"Template '{template_name}' not found"

    def test_all_templates_have_required_fields(self):
        """Test all templates have required fields."""
        for template_name, template in TASK_TEMPLATES.items():
            assert template.name == template_name
            assert template.title_template
            assert template.priority
            assert isinstance(template.tags, list)
            assert len(template.tags) > 0
            assert isinstance(template.acceptance_criteria, list)
            assert len(template.acceptance_criteria) > 0
            assert template.task_type in ["task", "bug", "feature"]

    def test_template_priorities_valid(self):
        """Test all templates have valid priorities."""
        valid_priorities = ["low", "medium", "high", "urgent"]
        for template in TASK_TEMPLATES.values():
            assert template.priority in valid_priorities


class TestApplyTemplate:
    """Test applying templates to create task data."""

    def test_apply_bug_template(self):
        """Test bug template application."""
        result = apply_template("bug", "Login fails on Firefox")

        assert "Bug Fix: Login fails on Firefox" in result["title"]
        assert result["priority"] == "high"
        assert "bug" in result["tags"]
        assert "urgent" in result["tags"]
        assert len(result["acceptance_criteria"]) > 0

    def test_apply_feature_template(self):
        """Test feature template application."""
        result = apply_template("feature", "Add dark mode")

        assert "Feature: Add dark mode" in result["title"]
        assert result["priority"] == "medium"
        assert "feature" in result["tags"]
        assert result["task_type"] == "feature"

    def test_apply_hotfix_template(self):
        """Test hotfix template application."""
        result = apply_template("hotfix", "Database connection timeout")

        assert "HOTFIX: Database connection timeout" in result["title"]
        assert result["priority"] == "urgent"
        assert "hotfix" in result["tags"]
        assert "critical" in result["tags"]

    def test_apply_research_template(self):
        """Test research template application."""
        result = apply_template("research", "Compare caching strategies")

        assert "Research: Compare caching strategies" in result["title"]
        assert result["priority"] == "low"
        assert "research" in result["tags"]

    def test_apply_meeting_template(self):
        """Test meeting template application."""
        result = apply_template("meeting", "Q1 Planning Session")

        assert "Meeting: Q1 Planning Session" in result["title"]
        assert result["priority"] == "medium"
        assert "meeting" in result["tags"]

    def test_apply_documentation_template(self):
        """Test documentation template application."""
        result = apply_template("documentation", "API Reference Guide")

        assert "Documentation: API Reference Guide" in result["title"]
        assert result["priority"] == "medium"
        assert "documentation" in result["tags"]

    def test_apply_review_template(self):
        """Test code review template application."""
        result = apply_template("review", "PR #123 - Auth System")

        assert "Code Review: PR #123 - Auth System" in result["title"]
        assert result["priority"] == "high"
        assert "review" in result["tags"]

    def test_apply_deployment_template(self):
        """Test deployment template application."""
        result = apply_template("deployment", "v2.1.0 to Production")

        assert "Deployment: v2.1.0 to Production" in result["title"]
        assert result["priority"] == "high"
        assert "deployment" in result["tags"]
        assert "prod" in result["tags"]

    def test_apply_template_with_overrides(self):
        """Test template with field overrides."""
        result = apply_template("feature", "Add API", priority="high", tags=["api", "backend"])

        assert result["priority"] == "high"  # Override applied
        assert "api" in result["tags"]  # Override applied
        assert "backend" in result["tags"]

    def test_apply_template_unknown_raises_error(self):
        """Test applying unknown template raises error."""
        with pytest.raises(ValueError) as exc_info:
            apply_template("unknown_template", "Description")

        assert "Unknown template" in str(exc_info.value)
        assert "available" in str(exc_info.value).lower()

    def test_apply_template_case_insensitive(self):
        """Test template names are case-insensitive."""
        result1 = apply_template("BUG", "Test bug")
        result2 = apply_template("bug", "Test bug")

        assert result1["priority"] == result2["priority"]
        assert result1["tags"] == result2["tags"]

    def test_apply_template_with_whitespace(self):
        """Test template names work with whitespace."""
        result = apply_template("  bug  ", "  Test bug  ")

        assert "Bug Fix:" in result["title"]
        assert "Test bug" in result["title"]


class TestGetTemplate:
    """Test retrieving individual templates."""

    def test_get_existing_template(self):
        """Test getting an existing template."""
        template = get_template("bug")

        assert template is not None
        assert template.name == "bug"
        assert template.priority == "high"

    def test_get_nonexistent_template(self):
        """Test getting a non-existent template."""
        template = get_template("nonexistent")

        assert template is None

    def test_get_template_case_insensitive(self):
        """Test template retrieval is case-insensitive."""
        template1 = get_template("BUG")
        template2 = get_template("bug")

        assert template1 is not None
        assert template2 is not None
        assert template1.name == template2.name


class TestValidateTemplate:
    """Test template name validation."""

    def test_validate_existing_templates(self):
        """Test validation of existing templates."""
        for template_name in TASK_TEMPLATES.keys():
            assert validate_template_name(template_name) is True

    def test_validate_nonexistent_template(self):
        """Test validation of non-existent template."""
        assert validate_template_name("nonexistent") is False

    def test_validate_template_case_insensitive(self):
        """Test validation is case-insensitive."""
        assert validate_template_name("BUG") is True
        assert validate_template_name("FEATURE") is True


class TestListTemplates:
    """Test listing available templates."""

    def test_list_templates_returns_dict(self):
        """Test list_templates returns a dictionary."""
        templates = list_templates()

        assert isinstance(templates, dict)
        assert len(templates) > 0

    def test_list_templates_has_descriptions(self):
        """Test all templates have descriptions."""
        templates = list_templates()

        for name, description in templates.items():
            assert isinstance(name, str)
            assert isinstance(description, str)
            assert len(description) > 0

    def test_list_templates_covers_all_templates(self):
        """Test list_templates includes all defined templates."""
        templates = list_templates()

        for template_name in TASK_TEMPLATES.keys():
            assert template_name in templates


class TestGetSuggestions:
    """Test template suggestions based on text."""

    def test_suggest_bug_template(self):
        """Test bug template suggestions."""
        suggestions = get_template_suggestions("The login feature is broken")

        assert "bug" in suggestions or "feature" in suggestions

    def test_suggest_hotfix_template(self):
        """Test hotfix template suggestions."""
        suggestions = get_template_suggestions("Critical production error")

        assert "hotfix" in suggestions

    def test_suggest_feature_template(self):
        """Test feature template suggestions."""
        suggestions = get_template_suggestions("Add dark mode support")

        assert "feature" in suggestions

    def test_suggest_research_template(self):
        """Test research template suggestions."""
        suggestions = get_template_suggestions("Investigate performance issues")

        assert "research" in suggestions

    def test_suggest_multiple_templates(self):
        """Test multiple template suggestions."""
        suggestions = get_template_suggestions("Deploy the new feature")

        assert isinstance(suggestions, list)
        # Could suggest feature or deployment

    def test_suggest_empty_suggestions(self):
        """Test no suggestions for generic text."""
        suggestions = get_template_suggestions("Update the thing")

        # Should return empty or generic suggestions
        assert isinstance(suggestions, list)


class TestFormatHelp:
    """Test help formatting."""

    def test_format_template_help_returns_string(self):
        """Test format_template_help returns a string."""
        help_text = format_template_help()

        assert isinstance(help_text, str)
        assert len(help_text) > 0

    def test_format_template_help_includes_all_templates(self):
        """Test help text includes all templates."""
        help_text = format_template_help()

        for template_name in TASK_TEMPLATES.keys():
            assert template_name in help_text.lower()

    def test_format_template_help_includes_usage(self):
        """Test help text includes usage instructions."""
        help_text = format_template_help()

        assert "template" in help_text.lower()
        assert "usage" in help_text.lower() or "example" in help_text.lower()


class TestTemplateIntegration:
    """Integration tests for template usage."""

    def test_create_all_templates(self):
        """Test creating tasks from all templates."""
        for template_name in TASK_TEMPLATES.keys():
            result = apply_template(template_name, f"Test {template_name} task")

            assert "title" in result
            assert "priority" in result
            assert "tags" in result
            assert "acceptance_criteria" in result

    def test_template_data_structure(self):
        """Test template data structure is correct for task creation."""
        result = apply_template("bug", "Test")

        # Verify it contains all fields needed for task creation
        required_fields = ["title", "priority", "tags", "acceptance_criteria", "task_type"]
        for field in required_fields:
            assert field in result, f"Missing field: {field}"

    def test_template_metadata(self):
        """Test template metadata is included."""
        result = apply_template("feature", "New API endpoint")

        assert "template_name" in result
        assert result["template_name"] == "feature"

    def test_acceptance_criteria_are_lists(self):
        """Test acceptance criteria are properly formatted as lists."""
        for template_name in TASK_TEMPLATES.keys():
            result = apply_template(template_name, "Test")

            assert isinstance(result["acceptance_criteria"], list)
            assert len(result["acceptance_criteria"]) > 0
            for criterion in result["acceptance_criteria"]:
                assert isinstance(criterion, str)
                assert len(criterion) > 0

    def test_estimated_effort_present_when_available(self):
        """Test estimated effort is included when available."""
        result = apply_template("bug", "Test")

        if result.get("estimated_effort"):
            assert isinstance(result["estimated_effort"], str)
            assert len(result["estimated_effort"]) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
