from flask import Flask, request, make_response, render_template
import json
from datetime import datetime, date
from decimal import Decimal

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

@app.route("/", methods=["GET"])
def index():
    return render_template('index.html')

@app.route("/ask", methods=["POST"])
def ask():
    # Support both JSON and form data
    if request.content_type and request.content_type.startswith("application/json"):
        data = request.get_json(force=True, silent=False)
    else:
        data = {
            "question": request.form.get("question", ""),
            "identity": {"user_id": int(request.form.get("user_id", "0") or 0)},
        }

    # Simulate response data - в реальном приложении здесь будет ваша логика
    simulated_response = {
        "sql": "SELECT * FROM tasks WHERE company_id = 1 AND created_at >= '2025-09-01'",
        "needs_clarification": False,
        "clarification_question": None,
        "rows": [
            {
                "id": 1,
                "title": "Задача 1",
                "description": "Описание задачи 1",
                "status": "completed",
                "priority": "high",
                "created_at": "2025-09-15T10:30:00",
                "assigned_to": "Иван Иванов"
            },
            {
                "id": 2,
                "title": "Задача 2", 
                "description": "Описание задачи 2",
                "status": "in_progress",
                "priority": "medium",
                "created_at": "2025-09-20T14:45:00",
                "assigned_to": "Петр Петров"
            },
            {
                "id": 3,
                "title": "Задача 3",
                "description": "Описание задачи 3",
                "status": "pending",
                "priority": "low", 
                "created_at": "2025-09-25T09:15:00",
                "assigned_to": "Мария Сидорова"
            }
        ],
        "explanation": "Выполнен запрос: Все задачи моей компании за сентябрь 2025. Найдено строк: 3."
    }

    return json_utf8(simulated_response)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)