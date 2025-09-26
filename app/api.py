from flask import Flask, request, make_response
import json
from datetime import datetime, date
from decimal import Decimal

from .models import AskRequest, AskResponse
from .db import fetch_one, fetch_all
from .schema_cache import schema_cache
from .safety import is_safe_select
from .sql_generator import generate_sql


app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False
# Ensure Flask 3 JSON provider does not escape non-ASCII
try:
    app.json.ensure_ascii = False
except Exception:
    pass
# Force JSON responses to declare UTF-8
app.config["JSONIFY_MIMETYPE"] = "application/json; charset=utf-8"


def _json_default(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    return str(obj)


def json_utf8(data, status: int = 200):
    body = json.dumps(data, ensure_ascii=False, default=_json_default)
    resp = make_response(body, status)
    resp.headers["Content-Type"] = "application/json; charset=utf-8"
    return resp


@app.route("/health", methods=["GET"])
def health():
    return json_utf8({"status": "ok"})


@app.route("/debug/schema", methods=["GET"])
def debug_schema():
    if not schema_cache.tables:
        try:
            schema_cache.load()
        except Exception as e:
            return json_utf8({"loaded": False, "error": str(e)}, 500)
    return json_utf8({
        "loaded": True,
        "tables_count": len(schema_cache.tables),
        "tables": sorted(list(schema_cache.tables.keys()))[:50],
        "fks_count": len(schema_cache.foreign_keys),
    })


@app.route("/", methods=["GET"])
def index():
    return (
        """
        <html>
          <head>
          <meta charset="UTF-8">
          <title>RAG-SQL Assistant</title></head>
          <body>
            <h2>RAG-SQL Assistant (Flask)</h2>
            <p>Service is running. Use <code>POST /ask</code> with JSON.</p>
            <pre>
curl -X POST http://localhost:8000/ask \
  -H 'Content-Type: application/json' \
  -d '{"question":"Все задачи моей компании за сентябрь 2025","identity":{"user_id":1}}'
            </pre>
            <p>Diagnostics: <a href="/debug/schema">/debug/schema</a>, <a href="/health">/health</a></p>
            <h3>Quick test form</h3>
            <form method="post" action="/ask">
              <label>Question: <input name="question" style="width: 400px" value="Все задачи моей компании за сентябрь 2025"/></label><br/>
              <label>User ID: <input name="user_id" value="1"/></label><br/>
              <button type="submit">Send</button>
            </form>
          </body>
        </html>
        """,
        200,
        {"Content-Type": "text/html; charset=utf-8"},
    )


@app.route("/ask", methods=["POST"])
def ask():
    # Ensure schema loaded
    if not schema_cache.tables:
        try:
            schema_cache.load()
        except Exception as e:
            return json_utf8({"detail": f"Failed to load schema: {e}"}, 500)
    if not schema_cache.tables:
        return json_utf8({
            "detail": "Schema is empty. Check POSTGRES_DSN and that your database has tables.",
            "hint": "export POSTGRES_DSN=postgresql://localhost:5432/tasks and restart app",
        }, 500)

    # Support simple form submission from the index page
    if request.content_type and request.content_type.startswith("application/json"):
        data = request.get_json(force=True, silent=False)
    else:
        data = {
            "question": request.form.get("question", ""),
            "identity": {"user_id": int(request.form.get("user_id", "0") or 0)},
        }

    try:
        req = AskRequest(**data)
    except Exception as e:
        return json_utf8({"detail": f"Invalid request: {e}"}, 400)

    user = fetch_one("SELECT * FROM public.users WHERE id = %(id)s", {"id": req.identity.user_id})
    if not user:
        return json_utf8({"detail": "Unknown user_id"}, 400)
    if req.identity.company_id is None and "company_id" in user:
        req.identity.company_id = user["company_id"]
    if req.identity.department_id is None and "department_id" in user:
        req.identity.department_id = user["department_id"]

    generated = generate_sql(req.question, req.identity, limit=req.limit)

    if not generated.sql or not is_safe_select(generated.sql):
        return json_utf8({"detail": "Unsafe or empty SQL", "sql": generated.sql}, 400)

    try:
        rows = fetch_all(generated.sql)
    except Exception as e:
        return json_utf8({"detail": f"SQL execution error: {e}", "sql": generated.sql}, 400)

    resp = AskResponse(
        sql=generated.sql,
        needs_clarification=generated.needs_clarification,
        clarification_question=generated.clarification_question,
        rows=rows,
        explanation=f"Выполнен запрос: {req.question}. Найдено строк: {len(rows)}.",
    )
    return json_utf8(resp.model_dump())


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
