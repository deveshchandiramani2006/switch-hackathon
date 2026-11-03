FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY shared/ ./shared/
COPY agents/support_agent/ ./agents/support_agent/
COPY company_config.yaml .
ENV PYTHONPATH=/app
CMD ["python", "-m", "agents.support_agent.main"]
