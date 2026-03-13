# ════════════════════════════════════════════════════════════════
#  Dockerfile — Sienna Bot (La Taverne)
# ════════════════════════════════════════════════════════════════

FROM python:3.11-slim

# Métadonnées
LABEL maintainer="La Taverne Bot"
LABEL description="Bot Discord Sienna — La Taverne"

# Dossier de travail
WORKDIR /app

# Dépendances système pour Pillow (images/GIF)
RUN apt-get update && apt-get install -y \
    libfreetype6-dev \
    libjpeg-dev \
    libpng-dev \
    libwebp-dev \
    fonts-liberation \
    fonts-dejavu-core \
    --no-install-recommends \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copier les dépendances Python en premier (cache Docker)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copier tous les fichiers du bot
COPY bot.py .
COPY stats_card.py .
COPY welcome_card.py .
COPY levelup_card.py .

# Copier les assets (images)
COPY ticket_banner.png .
COPY reglement_banner.png .
COPY taverne_bg.png .

# Dossier de données persistantes (monté comme volume)
RUN mkdir -p /app/data

# Variables d'environnement (à fournir via Railway ou .env)
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Lancement du bot
CMD ["python", "bot.py"]
