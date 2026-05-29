FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml /app/pyproject.toml
COPY src /app/src

RUN pip install --no-cache-dir .

ENV H59_DASHBOARD_HOST=0.0.0.0
ENV H59_DASHBOARD_PORT=8000

CMD ["python", "-m", "uvicorn", "h59_dashboard_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
