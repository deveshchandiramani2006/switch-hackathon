FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ ./app/
COPY config/ ./config/
COPY agents/cs_agent/ ./agents/cs_agent/
ENV PYTHONPATH=/app
CMD ["python", "agents/cs_agent/agent.py"]
