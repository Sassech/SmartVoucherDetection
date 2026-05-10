# Skill Registry — SmartVoucherDetection

**Generated**: 2026-05-09  
**Project**: SmartVoucherDetection

---

## Active Skills for This Project

### Python / FastAPI
- **fastapi** — `~/.config/opencode/skills/06_python/fastapi/SKILL.md`
  - Use for: project structure, async patterns, JWT auth, SQLAlchemy async, Pydantic V2, CORS, WebSockets, uv
  - Key rules: always async endpoints; use `Annotated` for DI; Pydantic v2 `.model_dump()` not `.dict()`

- **pytest** — `~/.config/opencode/skills/06_python/pytest/SKILL.md`
  - Use for: fixtures, mocking, markers, async tests
  - Key rules: `asyncio_mode=auto` already configured; use `pytest.mark.parametrize` for table tests

- **django-drf** — not applicable (project uses FastAPI)

### SDD Workflow
- **sdd-explore** — explore ideas before committing to a change
- **sdd-propose** — create change proposal
- **sdd-spec** — write delta specs with requirements and scenarios
- **sdd-design** — technical design and architecture approach
- **sdd-tasks** — break change into implementation tasks
- **sdd-apply** — implement from specs and design
- **sdd-verify** — execute tests and prove implementation matches specs
- **sdd-archive** — archive completed change by syncing delta specs

### DevOps / Infra
- **docker** — `~/.config/opencode/skills/02_devops/docker/SKILL.md`
  - Relevant for: `infra/docker-compose.yml`, production hardening
- **docker-compose-orchestration** — `~/.config/opencode/skills/02_devops/docker-compose/SKILL.md`
  - Relevant for: multi-service orchestration (postgres + redis)

### Code Quality
- **systematic-debugging** — `~/.opencode/skills/systematic-debugging/SKILL.md`
  - Use before any bug fix or test failure investigation
- **error-handling-patterns** — `~/.config/opencode/skills/01_global/error-handling-patterns/SKILL.md`
  - Use when implementing error handling across async service boundaries

### Database
- **postgresql-table-design** — `~/.config/opencode/skills/08_databases/postgresql/SKILL.md`
  - Relevant for: schema design, Alembic migrations, indexing

---

## Project-Level Convention Files

- `api/pyproject.toml` — dependencies, pytest config, coverage config
- `.pre-commit-config.yaml` — ruff lint/format hooks
- `PROGRESO.md` — development progress log
- `plan_desarrollo.md` — development plan

---

## Not Applicable

- angular-*, react-*, nextjs-*, vue → frontend skills (not used in api/)
- rust-* → wrong language
- wordpress (wp-*) → plugin-wp/ is a separate concern, not the main stack
