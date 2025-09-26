# RAG-SQL Assistant (Postgres + Flask)

## Setup
1. Create and start Postgres (or use your own):
```bash
docker run --name tasks-pg -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=tasks -p 5432:5432 -d postgres:16
psql "postgresql://postgres:postgres@localhost:5432/tasks" -f /Users/vik0t/hackatons/RAG-SQL-assistant/task_db_dump.sql
```

2. Python env and deps:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

3. Environment (optional):
- `POSTGRES_DSN` via `.env` or env var
- `READONLY_ROLE` optional DB role
- `OPENAI_API_KEY` to enable LLM generation

## Run (dev)
```bash
python -m app.api
```

## Run (prod)
```bash
gunicorn -w 2 -b 0.0.0.0:8000 app.api:app
```

## Use
POST http://localhost:8000/ask
```json
{
  "question": "Все задачи моей компании за сентябрь 2025",
  "identity": {"user_id": 1}
}
```

## Notes
- Vector DB is optional; current retriever uses schema/rules snippets.
- Add your few-shot examples and business rules for best results.
