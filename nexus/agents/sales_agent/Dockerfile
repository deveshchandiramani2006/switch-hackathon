FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY shared/ ./shared/
COPY agents/sales_agent/ ./agents/sales_agent/
COPY company_config.yaml .
ENV PYTHONPATH=/app
CMD ["python", "-m", "agents.sales_agent.main"]
