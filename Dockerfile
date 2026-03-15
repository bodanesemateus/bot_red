# Bot Red Card v2
# Python 3.11-slim + Playwright Stealth + fontes reais para canvas fingerprint
# Multi-arch: funciona em amd64 e arm64

FROM python:3.11-slim-bookworm AS base

# ── Variáveis de ambiente ──────────────────────────────────────────
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers \
    # Locale pt-BR para consistência com o site alvo
    LANG=pt_BR.UTF-8 \
    LC_ALL=pt_BR.UTF-8

# ── Dependências de sistema ────────────────────────────────────────
# Agrupadas por função para facilitar manutenção
RUN apt-get update && apt-get install -y --no-install-recommends \
    # --- Locale ---
    locales \
    # --- Chromium runtime deps (Playwright) ---
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libxkbcommon0 \
    libatspi2.0-0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    libwayland-client0 \
    # --- Fontes reais (evita canvas fingerprint vazio) ---
    fonts-liberation \
    fonts-noto-core \
    fonts-noto-color-emoji \
    fontconfig \
    # --- Libs gráficas para renderização completa ---
    libjpeg62-turbo \
    libpng16-16 \
    libwebp7 \
    # --- Build deps para curl_cffi ---
    curl \
    libcurl4-openssl-dev \
    libssl-dev \
    build-essential \
    # --- Display virtual (headless=False dentro do container) ---
    xvfb \
    xauth \
    # --- Networking ---
    ca-certificates \
    && sed -i '/pt_BR.UTF-8/s/^# //' /etc/locale.gen \
    && locale-gen pt_BR.UTF-8 \
    # Rebuild font cache com as novas fontes
    && fc-cache -fv \
    # Limpar cache do apt
    && rm -rf /var/lib/apt/lists/*

# ── Diretório de trabalho ──────────────────────────────────────────
WORKDIR /app

# ── Dependências Python (cache layer separado) ────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Instalar Chromium via Playwright ───────────────────────────────
# Instala apenas chromium (não precisa de firefox/webkit)
RUN playwright install chromium

# ── Código-fonte ───────────────────────────────────────────────────
COPY main.py .
COPY src/ ./src/

# ── Segurança: usuário não-root ───────────────────────────────────
RUN useradd --create-home --shell /bin/bash botuser \
    && chown -R botuser:botuser /opt/pw-browsers \
    && chown -R botuser:botuser /app

USER botuser

# ── Healthcheck ────────────────────────────────────────────────────
HEALTHCHECK --interval=60s --timeout=10s --retries=3 \
    CMD python -c "from playwright.sync_api import sync_playwright; print('ok')"

# ── Entrypoint ─────────────────────────────────────────────────────
CMD ["python", "main.py"]
