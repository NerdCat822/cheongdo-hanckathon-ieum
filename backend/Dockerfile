FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt \
    && COPILOT_CLI_EXTRACT_DIR=/opt/copilot-runtime python -m copilot download-runtime \
    && chmod -R a+rX /opt/copilot-runtime \
    && useradd --system --uid 10001 --create-home appuser
ENV COPILOT_CLI_EXTRACT_DIR=/opt/copilot-runtime COPILOT_SKIP_CLI_DOWNLOAD=1
COPY backend/ /app/backend/

USER appuser
EXPOSE 8000
CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
