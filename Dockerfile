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
    libsqlite3-dev \
    libsqlite3-mod-spatialite \  
    libspatialite7 \
    gdal-bin \                   
    libgdal-dev \                 
    libgeos-dev \
    libproj-dev \
    libxml2 libxslt1.1 libffi-dev \
    # WeasyPrint deps 👇
    libcairo2 \
    pango1.0-tools \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 \
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

# Static files will be collected at runtime

# Expose default port
EXPOSE 8000

# Add entrypoint for certificate reconstruction
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]

# Run the app with Gunicorn
CMD ["gunicorn", "backend.wsgi:application", "--bind", "0.0.0.0:8000"]
