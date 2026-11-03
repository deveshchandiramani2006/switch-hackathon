FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY shared/ ./shared/
COPY agents/geo_seo_agent/ ./agents/geo_seo_agent/
COPY company_config.yaml .
ENV PYTHONPATH=/app
CMD ["python", "-m", "agents.geo_seo_agent.main"]
