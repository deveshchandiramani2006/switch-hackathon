FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ ./app/
COPY config/ ./config/
COPY agents/sales_agent/ ./agents/sales_agent/
ENV PYTHONPATH=/app
CMD ["python", "agents/sales_agent/agent.py"]
