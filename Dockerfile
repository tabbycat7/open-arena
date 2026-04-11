FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install Python dependencies first to leverage Docker layer caching.
COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt gunicorn

# Copy project files.
COPY . .

EXPOSE 5500

CMD ["sh", "-c", "python init_db.py && gunicorn -w 2 -b 0.0.0.0:5500 app:app"]
