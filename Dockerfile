FROM python:3.12-slim

WORKDIR /app

# Backend dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend
COPY backend/ backend/
COPY cli/ cli/

# Data directory
RUN mkdir -p /root/.nexsys

# Init data
RUN python -m cli.main init

EXPOSE 8420

CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8420"]
