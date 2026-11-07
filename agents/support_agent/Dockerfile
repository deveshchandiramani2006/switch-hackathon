FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ ./app/
COPY config/ ./config/
COPY agents/support_agent/ ./agents/support_agent/
ENV PYTHONPATH=/app
CMD ["python", "agents/support_agent/agent.py"]
