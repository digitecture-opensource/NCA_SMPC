FROM python:3.11-slim-bookworm

# Install MS ODBC Driver 18 for SQL Server + deps (Microsoft repo package)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates gnupg2 apt-transport-https \
    unixodbc unixodbc-dev \
 && curl -fsSL https://packages.microsoft.com/config/debian/12/packages-microsoft-prod.deb -o /tmp/packages-microsoft-prod.deb \
 && dpkg -i /tmp/packages-microsoft-prod.deb \
 && rm -f /tmp/packages-microsoft-prod.deb \
 && apt-get update \
 && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 \
 && rm -rf /var/lib/apt/lists/*
 
WORKDIR /app

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app/

ENV DJANGO_DEBUG=0
RUN python manage.py collectstatic --noinput || true

EXPOSE 8000

CMD ["sh", "-c", "python manage.py migrate --run-syncdb && gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 2 --timeout 120"]