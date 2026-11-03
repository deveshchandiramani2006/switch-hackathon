FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY shared/ ./shared/
COPY agents/blog_agent/ ./agents/blog_agent/
COPY company_config.yaml .
ENV PYTHONPATH=/app
CMD ["python", "-m", "agents.blog_agent.main"]
