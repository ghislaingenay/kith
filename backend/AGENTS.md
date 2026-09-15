# AGENTS.md

## Project

Python 3.11+ backend using FastAPI, Pydantic v2, SQLAlchemy 2.0, and `dependency-injector`.

The project follows a strict domain/module-oriented architecture.

## Mandatory Instructions

Before creating or modifying code:

1. Read `context/coding-standards.md`.
2. Follow all architectural and coding rules defined there.
3. Inspect the existing domain/module structure before creating new files.
4. Reuse existing abstractions and patterns before introducing new ones.
5. Do not introduce a new architectural pattern without a concrete reason.

## Architecture

- Application code lives under `src/`.
- Organize code by business domain/module.
- Keep FastAPI routes thin.
- Keep business logic inside its owning domain.
- Keep persistence in repositories.
- Use dependency injection.
- Keep infrastructure replaceable.
- Do not create an `application/` layer unless explicitly requested.
- Do not create global `services/`, `repositories/`, `controllers/`, or `models/` folders.

## Context

Detailed coding and architecture rules:

`context/coding-standards.md`

When additional context files exist under `context/`, read the relevant file before working in that area.

## Implementation Rules

Before completing a task:

- Check that the implementation follows `context/coding-standards.md`.
- Check existing code for consistency.
- Add or update tests for changed behavior.
- Do not leave unnecessary abstractions, dead code, or unused dependencies.
- Do not change unrelated code.

## Priority

When instructions conflict:

1. Explicit user requirements
2. `AGENTS.md`
3. Relevant files in `context/`
4. Existing project conventions
5. General framework conventions

Do not guess when a conflict materially affects architecture or behavior. Ask for clarification.
