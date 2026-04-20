# Gemma DB Chat Agent

This project creates an AI agent that can:

- connect to a structured database using a SQLAlchemy URI
- analyze database schema and sample data
- let users chat with the database in natural language
- use a local Gemma model via Ollama to generate SQL and responses

## Features

- Works with any SQLAlchemy-supported structured database:
  - SQLite
  - PostgreSQL
  - MySQL/MariaDB
  - SQL Server
  - Oracle
- Automatic schema inspection
- Lightweight table profiling (row count + sample rows)
- Conversational SQL generation (non-deterministic)
- Interactive chat loop

## Quick Start

1. Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Start Ollama and pull a model available on your machine:

```bash
ollama pull gemma:7b
```

4. Copy environment file and edit if needed:

```bash
cp .env.example .env
```

5. Run schema/data analysis:

```bash
python run.py analyze --db-uri "sqlite:///example.db"
```

6. Start interactive chat:

```bash
LLM_MODEL=gemma:7b python run.py chat --db-uri "sqlite:///example.db"
```

## Configuration

Set values in `.env` or as environment variables:

- `LLM_PROVIDER`: `ollama` (default) or `openai_compatible`
- `LLM_BASE_URL`: default `http://localhost:11434`
- `LLM_MODEL`: default `gemma3:8b`
- `LLM_API_KEY`: only needed for openai-compatible endpoints
- `MAX_RESULT_ROWS`: max rows returned from each generated query (default `200`)
- `LLM_TIMEOUT_SECONDS`: LLM request timeout in seconds (default `120`)
- `LLM_MAX_TOKENS`: response token cap per model call (default `256`)
- `SQL_RETRY_ATTEMPTS`: retries for SQL generation when output is invalid (default `3`)
- `CONVERSATION_HISTORY_TURNS`: number of prior turns included in SQL prompt context (default `3`)

## DB URI Examples

- SQLite: `sqlite:///example.db`
- PostgreSQL: `postgresql+psycopg://user:pass@localhost:5432/mydb`
- MySQL: `mysql+pymysql://user:pass@localhost:3306/mydb`

Note: install driver packages for non-SQLite databases as needed.

## Safety Notes

- SQL execution guardrails are currently disabled in code.
- Generated SQL is executed directly against the connected database.
- Use a read-only DB user and non-production data unless you fully trust the model output.
