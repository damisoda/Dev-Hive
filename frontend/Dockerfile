FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8501

# Funnel(HTTPS 프록시) 뒤에서 동작 — CORS/XSRF는 프록시 신뢰로 완화
CMD ["streamlit", "run", "app.py", "--server.port", "8501", "--server.address", "0.0.0.0", \
     "--server.headless", "true", "--browser.gatherUsageStats", "false", \
     "--server.enableCORS", "false", "--server.enableXsrfProtection", "false"]
