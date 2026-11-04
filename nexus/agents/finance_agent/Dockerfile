FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ ./app/
COPY config/ ./config/
COPY agents/finance_agent/ ./agents/finance_agent/
ENV PYTHONPATH=/app
CMD ["python", "agents/finance_agent/agent.py"]
