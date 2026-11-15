# Олимпиадный дашборд

FastAPI + SQLite + vanilla JS.

## Запуск
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload