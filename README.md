# Chur

A family finance manager backend.

Settings are read from environment variables prefixed with `CHUR_`. See
`plan.md` for the build plan.

## UV

This project uses uv. It's a modern dependency management
tool.

To run the project use this set of commands:

```bash
uv sync --locked
uv run uvicorn app.main:app --reload
```

This will start the server on `http://127.0.0.1:8000`.

You can find swagger documentation at `/api/docs`.

You can read more about uv here: https://docs.astral.sh/ruff/

## Docker

You can start the project with docker using this command:

```bash
docker compose up --build
```

This command exposes the web application on port 8000, mounts current directory and enables autoreload.

But you have to rebuild image every time you modify `uv.lock` or `pyproject.toml` with this command:

```bash
docker compose build
```

## Project structure

```bash
$ tree "app"
app
├── api  # REST handlers, routers and per-feature dependency wiring.
│   ├── dependencies  # Per-feature FastAPI dependency providers (db session, services, auth/role checks). The only place allowed to use `fastapi.Depends`.
│   ├── middlewares  # Custom ASGI middlewares.
│   ├── v1  # Versioned resources: v1/<name>/{routes.py,schema.py}.
│   └── router.py  # Main REST router, mounts v1 under `/v1`.
├── config
│   └── settings.py  # Main configuration settings for project.
├── dal  # Data access layer: low-level, ORM-specific database queries. Plain classes, no FastAPI.
├── db  # Database configuration: engine/session, metadata, models.
├── lifespan.py  # Actions to perform on startup and shutdown -- builds services onto app.state.
├── libs  # Low-level integrations with queues and third-party services.
├── main.py  # The FastAPI `app`, nothing else. Started via uvicorn/gunicorn on the command line.
├── services  # Business logic. Plain classes built on dal + libs objects, no FastAPI.
├── static  # Static content.
├── tasks  # Taskiq broker and task definitions.
└── tests  # Fixtures and tests for the project.
```

A few rules keep this layout meaningful as the project grows:

* `api`/`gql`/CLI commands never talk to `dal` or `libs` directly -- they call `services`.
* `dal`, `libs` and `services` are plain Python: no `fastapi.Depends`, no framework glue. `app/api/dependencies/` (and `app/gql/context.py` for GraphQL) is the *only* place allowed to use FastAPI's dependency injection: it either reads an object built once at startup off `request.app.state` (see `app/lifespan.py`), or composes a `dal`/`services` object for the current request. A service describes *what* it does; `api`/`gql` wire up *how* it's constructed.
* Permission checks (who is allowed to do what) live in a service (e.g. `PermissionService`), not in a router or resolver. Each transport surface (`api/dependencies/permissions.py`, `gql/permissions`, ...) only translates that decision into the right error for its protocol.

## Configuration

This application can be configured with environment variables.

You can create `.env` file in the root directory and place all
environment variables here. 

All environment variables should start with "CHUR_" prefix.

For example if you see in your "app/config/settings.py" a variable named like
`random_parameter`, you should provide the "CHUR_RANDOM_PARAMETER" 
variable to configure the value. This behaviour can be changed by overriding `env_prefix` property
in `app.config.settings.Settings.Config`.

An example of .env file:
```bash
CHUR_ENVIRONMENT="dev"
```

Host and port aren't application settings -- they're passed directly to
uvicorn/gunicorn on the command line (see the Dockerfile and
`docker compose`'s `command:` override).

You can read more about BaseSettings class here: https://pydantic-docs.helpmanual.io/usage/settings/

## Pre-commit

To install pre-commit simply run inside the shell:
```bash
pre-commit install
```

pre-commit is very useful to check your code before publishing it.
It's configured using .pre-commit-config.yaml file.

By default it runs:
* mypy (validates types);
* ruff (spots possible bugs);


You can read more about pre-commit here: https://pre-commit.com/

## Migrations

If you want to migrate your database, you should run following commands:
```bash
# To run all migrations until the migration with revision_id.
alembic upgrade "<revision_id>"

# To perform all pending migrations.
alembic upgrade "head"
```

### Reverting migrations

If you want to revert migrations, you should run:
```bash
# revert all migrations up to: revision_id.
alembic downgrade <revision_id>

# Revert everything.
 alembic downgrade base
```

### Migration generation

To generate migrations you should run:
```bash
# For automatic change detection.
alembic revision --autogenerate

# For empty file generation.
alembic revision
```


## Running tests

If you want to run it in docker, simply run:

```bash
docker compose run --build --rm api pytest -vv .
docker compose down
```

For running tests on your local machine.
1. you need to start all aux services.

We can do so by using our `docker-compose.yaml` configuration. It already has everything we need.

```bash
docker compose up -d --wait db redis
```

2. Run tests.
```bash
pytest -vv .
```

