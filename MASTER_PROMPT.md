# MASTER PROMPT - Boss Workflow Development

Copy this prompt when starting a new Claude Code session for Boss Workflow development.

---

## START OF MASTER PROMPT

I'm working on the **Boss Workflow** project at `C:\Users\User\Desktop\ACCWARE.AI\AUTOMATION\boss-workflow`.

**Before doing anything:**
1. Read `FEATURES.md` to understand existing functionality
2. Read `CLAUDE.md` for development rules and workflow

**TASK:** [DESCRIBE YOUR TASK HERE]

**Follow this sequential workflow:**

### Phase 1: Brainstorm
Use `/brainstorming` skill to explore approaches. Present 2-4 options, recommend the BEST (not simplest), and ASK ME which approach before implementing.

### Phase 2: Plan
Use `/writing-plans` skill to create a detailed implementation plan. Include:
- Files to modify
- Changes per file
- Testing strategy
- Risks/considerations

### Phase 3: Implement
Use `/ralph-loop` or `/subagent-driven-development` for iterative implementation. After each change:
- Commit with clear message
- Push to trigger Railway deploy
- Wait for deploy, then test

### Phase 4: Test
Run specialized tests:
```bash
python test_full_loop.py test-simple     # Simple task flow
python test_full_loop.py test-complex    # Complex task flow
python test_full_loop.py test-routing    # Role-based routing
python test_full_loop.py test-all        # All tests
```

Pre/post deployment:
```bash
python test_full_loop.py verify-deploy   # Health check
python test_full_loop.py check-logs      # Error scan
```

### Phase 5: Review
Use `/code-review` or `/requesting-code-review` before merging.

### Phase 6: Summary
Provide end-of-workflow summary with:
1. What was implemented (files changed)
2. What was tested (results)
3. Commits made (hashes)
4. Status (complete/partial/blocked)
5. Next steps (if any)

**Key Rules:**
- ALWAYS ask before implementing when multiple approaches exist
- ALWAYS test with `test_full_loop.py` before marking complete
- ALWAYS verify deployment with `verify-deploy`
- ALWAYS provide end-of-workflow summary
- Update `FEATURES.md` LAST after changes

**Session continuity:**
```bash
python test_full_loop.py save-progress "task description"  # Save progress
python test_full_loop.py resume                            # Resume later
```

## END OF MASTER PROMPT

---

## Quick Reference

### Skills to Use
| Phase | Skill | Purpose |
|-------|-------|---------|
| Brainstorm | `/brainstorming` | Explore approaches |
| Plan | `/writing-plans` | Create implementation plan |
| Implement | `/ralph-loop` | Iterative development |
| Review | `/code-review` | Pre-merge review |
| Debug | `/systematic-debugging` | Fix issues |
| TDD | `/test-driven-development` | Write tests first |

### Test Commands
| Command | Purpose |
|---------|---------|
| `test-simple` | Verify simple tasks skip questions |
| `test-complex` | Verify complex tasks ask questions |
| `test-routing` | Verify role-based channel routing |
| `test-all` | Run complete test suite |
| `verify-deploy` | Check Railway deployment health |
| `check-logs` | Scan for errors in logs |
| `save-progress` | Save session state |
| `resume` | Load saved session state |

### Git Workflow
```bash
git add .
git commit -m "feat/fix/docs: description"
git push origin master
# Railway auto-deploys on push
```

### Railway Commands
```bash
railway logs -s boss-workflow           # View logs
railway redeploy -s boss-workflow --yes # Manual redeploy
railway status -s boss-workflow         # Check status
```
