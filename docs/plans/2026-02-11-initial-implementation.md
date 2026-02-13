# Awe AgentCheck Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the first working version of a multi-CLI orchestration platform with full-flow task execution, medium quality gate, PostgreSQL persistence, and local observability hooks.

**Architecture:** A FastAPI service hosts LangGraph-like orchestration state transitions, writes task artifacts to disk, persists task/turn/gate records in PostgreSQL via SQLAlchemy, and exposes API endpoints for CLI and Web clients. CLI commands trigger task creation and execution; a minimal Web panel reads the same API.

**Tech Stack:** Python 3.10+, FastAPI, SQLAlchemy, Pydantic, PostgreSQL, OpenTelemetry SDK, pytest.

---

### Task 1: Bootstrap project layout and dependencies

**Files:**
- Create: `pyproject.toml`
- Create: `README.md`
- Create: `.gitignore`
- Create: `src/awe_agentcheck/__init__.py`

**Step 1: Write failing test**
- Add import smoke test for package module.

**Step 2: Verify failure**
- Run import test before package files exist.

**Step 3: Implement minimal package scaffold**
- Add package init and metadata.

**Step 4: Verify passing**
- Re-run import smoke test.

### Task 2: Domain core and medium gate (TDD)

**Files:**
- Create: `src/awe_agentcheck/domain/models.py`
- Create: `src/awe_agentcheck/domain/gate.py`
- Test: `tests/unit/test_domain_state.py`
- Test: `tests/unit/test_gate.py`

**Step 1: Write failing tests for state transitions and gate logic**

**Step 2: Run tests to confirm failures**

**Step 3: Implement minimal domain logic**

**Step 4: Re-run tests for green**

### Task 3: Artifact writer and task workspace model (TDD)

**Files:**
- Create: `src/awe_agentcheck/storage/artifacts.py`
- Test: `tests/unit/test_artifacts.py`

**Step 1: Write failing tests for task workspace creation and index files**

**Step 2: Confirm failures**

**Step 3: Implement artifact writer**

**Step 4: Confirm pass**

### Task 4: API service, database, orchestration service

**Files:**
- Create: `src/awe_agentcheck/config.py`
- Create: `src/awe_agentcheck/db.py`
- Create: `src/awe_agentcheck/repository.py`
- Create: `src/awe_agentcheck/service.py`
- Create: `src/awe_agentcheck/api.py`
- Create: `src/awe_agentcheck/main.py`
- Test: `tests/unit/test_service.py`
- Test: `tests/unit/test_api.py`

**Step 1: Write failing service/API tests**

**Step 2: Verify failures**

**Step 3: Implement minimal API/service/repository flow**

**Step 4: Verify tests pass**

### Task 5: CLI entrypoint + minimal web panel + observability setup

**Files:**
- Create: `src/awe_agentcheck/cli.py`
- Create: `src/awe_agentcheck/observability.py`
- Create: `web/index.html`
- Create: `docker-compose.observability.yml`

**Step 1: Write failing smoke tests for CLI command parsing and endpoint reachability helpers**

**Step 2: Confirm failures**

**Step 3: Implement CLI and minimal web/static panel plus OTel bootstrap**

**Step 4: Verify test suite and package import pass**

### Task 6: Final verification and handoff notes

**Files:**
- Update: `README.md`

**Step 1: Run full test suite**
- Run: `py -m pytest -q`

**Step 2: Run package entry help checks**
- Run: `py -m awe_agentcheck.cli --help`

**Step 3: Document quickstart and known gaps**

**Step 4: Provide implementation summary with validated outputs**
