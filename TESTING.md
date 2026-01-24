# Testing Guide

Comprehensive testing documentation for the Boss Workflow system.

## Overview

The Boss Workflow system has comprehensive test coverage:
- **Unit Tests:** 380+ tests for handlers, repositories, and utilities
- **Integration Tests:** 130+ tests for external integrations
- **Coverage:** ~65% (target: 70%+)
- **Pass Rate:** 98%+

## Running Tests

### Basic Commands

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=src --cov-report=html

# Run integration tests
python test_full_loop.py test-all
```

### Test Categories

```bash
# Handler tests
pytest tests/unit/test_*_handler.py -v

# Repository tests
pytest tests/unit/repositories/ -v

# Integration tests
pytest tests/integration/ -v
```

## Test Statistics

```
Total Tests: 470+
├─ Handler Tests: 70+
├─ Repository Tests: 220+
├─ Integration Tests: 130+
├─ API Tests: 47+
└─ Security Tests: 40+
```

---

**Last Updated:** 2026-01-25
**Coverage:** ~65%
**Pass Rate:** 98%+
