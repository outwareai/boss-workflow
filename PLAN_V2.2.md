# Boss Workflow v2.2 Implementation Plan

## Overview
Upgrade the AI system to be smarter, ask questions only when needed, and route tasks to the right people automatically.

## Goals
1. **Smart Complexity Detection** - Only ask questions for complex tasks
2. **Role-Aware Intelligence** - Mayank = dev tasks, Zea = admin tasks
3. **Better Understanding** - Improved title/description generation
4. **Smarter Defaults** - Priority, deadline, effort from context

---

## Phase 1: Complexity Detection System

### File: `src/ai/clarifier.py`

**Add complexity scoring function:**
```python
def _calculate_task_complexity(self, message: str, analysis: dict) -> int:
    """
    Score task complexity 1-10:
    1-3: Simple (fix typo, small change) → No questions
    4-6: Medium (feature, refactor) → 1-2 key questions only
    7-10: Complex (new system, integration) → Full clarification
    """
    score = 3  # Base score

    # Increase for complexity signals
    if any(word in message.lower() for word in ['system', 'architecture', 'integration', 'design']):
        score += 3
    if any(word in message.lower() for word in ['multiple', 'several', 'complex', 'comprehensive']):
        score += 2
    if len(message) > 200:  # Long messages = more complex
        score += 1
    if 'subtask' in message.lower() or message.count(',') > 3:
        score += 2

    # Decrease for simplicity signals
    if any(word in message.lower() for word in ['fix', 'typo', 'small', 'quick', 'simple', 'minor']):
        score -= 2
    if any(word in message.lower() for word in ['no questions', 'just do', 'straightforward']):
        score -= 3

    return max(1, min(10, score))
```

**Modify question logic:**
```python
# In analyze_and_clarify():
complexity = self._calculate_task_complexity(message, analysis)

if complexity <= 3:
    # Simple task - self-answer everything
    can_proceed = True
    analysis["suggested_questions"] = []
    logger.info(f"Simple task (complexity={complexity}) - skipping questions")
elif complexity <= 6:
    # Medium task - ask only critical missing info
    critical_missing = [q for q in questions if q.get('critical', False)]
    analysis["suggested_questions"] = critical_missing[:2]  # Max 2 questions
elif complexity > 6:
    # Complex task - full clarification
    analysis["suggested_questions"] = questions[:4]  # Max 4 questions
```

---

## Phase 2: Role-Aware Intelligence

### File: `src/ai/clarifier.py`

**Add role-based defaults:**
```python
ROLE_DEFAULTS = {
    "developer": {
        "task_type": "feature",
        "priority": "medium",
        "effort": "4h",
        "tags": ["dev", "code"],
        "description_style": "technical"
    },
    "admin": {
        "task_type": "task",
        "priority": "medium",
        "effort": "2h",
        "tags": ["admin", "process"],
        "description_style": "process-focused"
    },
    "marketing": {
        "task_type": "task",
        "priority": "medium",
        "effort": "3h",
        "tags": ["marketing", "content"],
        "description_style": "creative"
    },
    "design": {
        "task_type": "design",
        "priority": "medium",
        "effort": "6h",
        "tags": ["design", "ui"],
        "description_style": "visual"
    }
}

def _get_role_defaults(self, assignee: str) -> dict:
    """Get smart defaults based on assignee's role."""
    role = self._lookup_assignee_role(assignee)
    if not role:
        return ROLE_DEFAULTS["developer"]  # Default

    role_lower = role.lower()
    if any(k in role_lower for k in ["dev", "engineer", "backend", "frontend"]):
        return ROLE_DEFAULTS["developer"]
    elif any(k in role_lower for k in ["admin", "manager", "lead", "director"]):
        return ROLE_DEFAULTS["admin"]
    elif any(k in role_lower for k in ["market", "content", "social", "growth"]):
        return ROLE_DEFAULTS["marketing"]
    elif any(k in role_lower for k in ["design", "ui", "ux", "graphic"]):
        return ROLE_DEFAULTS["design"]

    return ROLE_DEFAULTS["developer"]
```

### File: `src/integrations/discord.py`

**Improve keyword → role mapping:**
```python
TASK_KEYWORD_ROLES = {
    # Dev keywords
    "bug": "developer",
    "fix": "developer",
    "code": "developer",
    "api": "developer",
    "database": "developer",
    "deploy": "developer",
    "refactor": "developer",
    "test": "developer",

    # Admin keywords
    "meeting": "admin",
    "schedule": "admin",
    "report": "admin",
    "document": "admin",
    "process": "admin",
    "review": "admin",
    "approve": "admin",

    # Marketing keywords
    "campaign": "marketing",
    "social": "marketing",
    "content": "marketing",
    "email": "marketing",
    "influencer": "marketing",

    # Design keywords
    "design": "design",
    "mockup": "design",
    "ui": "design",
    "logo": "design",
    "graphic": "design"
}

def _infer_role_from_keywords(self, task_title: str, task_description: str) -> str:
    """Infer the appropriate role from task content."""
    text = f"{task_title} {task_description}".lower()

    role_scores = {"developer": 0, "admin": 0, "marketing": 0, "design": 0}
    for keyword, role in TASK_KEYWORD_ROLES.items():
        if keyword in text:
            role_scores[role] += 1

    if max(role_scores.values()) > 0:
        return max(role_scores, key=role_scores.get)
    return "developer"  # Default
```

---

## Phase 3: Enhanced Prompts

### File: `src/ai/prompts.py`

**Update TASK_ANALYSIS_PROMPT:**
```python
TASK_ANALYSIS_PROMPT_V2_2 = """
You are an intelligent task analyzer for Boss Workflow v2.2.

SMART UNDERSTANDING RULES:
1. If the message is clear and simple, extract everything without questions
2. Only flag missing info if it's TRULY ambiguous
3. Use context clues to infer priority, deadline, effort
4. Match assignee to the best person based on task type

COMPLEXITY SIGNALS:
- Simple: "fix typo", "update text", "small change" → complexity: low
- Medium: "add feature", "refactor", "integrate" → complexity: medium
- Complex: "build system", "redesign", "migrate" → complexity: high

ASSIGNEE INTELLIGENCE:
- If task mentions code/bug/api → likely for developer
- If task mentions process/meeting/report → likely for admin
- If task mentions content/social/campaign → likely for marketing
- If task mentions design/ui/mockup → likely for designer

WHEN TO INFER vs ASK:
- Deadline not specified + not urgent → infer "no deadline"
- Priority not specified + no urgency words → infer "medium"
- Assignee not specified + clear role → suggest based on keywords
- Assignee not specified + ambiguous → ASK (only this case)

Return JSON:
{
    "title": "clear, action-oriented title",
    "description": "detailed description",
    "assignee": "name or null if truly ambiguous",
    "suggested_assignee": "name if inferred from keywords",
    "priority": "low/medium/high/urgent",
    "deadline": "extracted or null",
    "effort": "estimated hours",
    "complexity": "low/medium/high",
    "confidence": 0.0-1.0,
    "missing_critical": ["only truly missing critical fields"],
    "inferred_fields": ["fields you intelligently filled in"]
}
"""
```

---

## Phase 4: Test Cases

### Test with `test_full_loop.py`

**Simple tasks (should NOT ask questions):**
```bash
python test_full_loop.py full-test "Task for Mayank: fix the login typo"
# Expected: Creates task immediately, no questions

python test_full_loop.py full-test "Zea needs to update the meeting notes"
# Expected: Creates admin task for Zea, routed to admin channel
```

**Medium tasks (1-2 questions max):**
```bash
python test_full_loop.py full-test "Mayank should refactor the authentication system"
# Expected: Maybe asks about scope or deadline, then creates
```

**Complex tasks (full clarification):**
```bash
python test_full_loop.py full-test "Build a complete notification system with email, SMS, and push notifications"
# Expected: Asks 3-4 clarifying questions before creating
```

**Role routing tests:**
```bash
python test_full_loop.py full-test "Task for Mayank: fix the API bug"
# Expected: Routes to DEV forum channel

python test_full_loop.py full-test "Task for Zea: schedule the team meeting"
# Expected: Routes to ADMIN channel
```

---

## Phase 5: Deployment

1. Make changes to files
2. Run local tests: `python test_all.py`
3. Deploy: `railway redeploy -s boss-workflow --yes`
4. Test with `test_full_loop.py`
5. Verify in Railway logs
6. Check Discord for correct routing

---

## Files to Modify

| File | Changes |
|------|---------|
| `src/ai/clarifier.py` | Add complexity scoring, role defaults |
| `src/ai/prompts.py` | Update TASK_ANALYSIS_PROMPT for v2.2 |
| `src/ai/intent.py` | Minor: Add complexity to extracted_data |
| `src/integrations/discord.py` | Add keyword → role inference |
| `src/bot/handler.py` | Wire complexity to question logic |

---

## Success Criteria

1. Simple tasks create immediately without questions
2. Complex tasks still get proper clarification
3. Mayank gets dev tasks routed to dev channel
4. Zea gets admin tasks routed to admin channel
5. Task titles are clear and action-oriented
6. All tests pass with `test_full_loop.py`

---

## Version

**Target:** v2.2.0
**Codename:** "Smart AI"
**Date:** 2026-01-23
