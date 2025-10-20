# syntax=docker/dockerfile:1
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV POETRY_VERSION=1.8.2

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    curl \
    unzip \
    libsqlite3-dev \
    libsqlite3-mod-spatialite \
    libspatialite8 \
    gdal-bin \
    libgdal-dev \
    libgeos-dev \
    libproj-dev \
    libxml2 libxslt1.1 libffi-dev \
    # WeasyPrint deps 👇
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libjpeg-dev \
    fonts-liberation \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN curl -sSL https://install.python-poetry.org | python3 - && \
    ln -s /root/.local/bin/poetry /usr/local/bin/poetry

# Copy only necessary files to install dependencies
COPY pyproject.toml poetry.lock ./

# Install dependencies in virtualenv and export to system
RUN poetry config virtualenvs.create false && \
    poetry install --no-interaction --no-ansi --without dev

# Copy the rest of the code
COPY . .

# Download and install Ubuntu font for WeasyPrint PDF generation
RUN mkdir -p /usr/share/fonts/truetype/ubuntu/ && \
    curl -L -o /tmp/Ubuntu-Regular.ttf "https://github.com/google/fonts/raw/main/ufl/ubuntu/Ubuntu-Regular.ttf" && \
    curl -L -o /tmp/Ubuntu-Bold.ttf "https://github.com/google/fonts/raw/main/ufl/ubuntu/Ubuntu-Bold.ttf" && \
    curl -L -o /tmp/Ubuntu-Italic.ttf "https://github.com/google/fonts/raw/main/ufl/ubuntu/Ubuntu-Italic.ttf" && \
    curl -L -o /tmp/Ubuntu-BoldItalic.ttf "https://github.com/google/fonts/raw/main/ufl/ubuntu/Ubuntu-BoldItalic.ttf" && \
    curl -L -o /tmp/Ubuntu-Light.ttf "https://github.com/google/fonts/raw/main/ufl/ubuntu/Ubuntu-Light.ttf" && \
    curl -L -o /tmp/Ubuntu-Medium.ttf "https://github.com/google/fonts/raw/main/ufl/ubuntu/Ubuntu-Medium.ttf" && \
    mv /tmp/Ubuntu-*.ttf /usr/share/fonts/truetype/ubuntu/ && \
    fc-cache -f -v

# Static files will be collected at runtime

# Expose default port
EXPOSE 8000

# Add entrypoint for certificate reconstruction
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]

# Run the app with Gunicorn
# Workers: 4 pour production Railway (formule: 2 × CPU + 1)
#   - Gère 2-4 requêtes simultanées (génération PDF CPU-intensive 30-60s)
#   - TSA interne (Python direct) = zéro risque de deadlock
# --timeout 120 : Timeout de 2min pour la génération de PDF et l'horodatage TSA
CMD ["gunicorn", "backend.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "4", "--timeout", "120"]
