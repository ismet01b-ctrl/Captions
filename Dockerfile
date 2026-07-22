# DouchkoVE Web-Server. Volles python:3.12-Image + alle Deps die
# opencv/mediapipe/PIL/onnxruntime/ffmpeg im Container ueblicherweise wollen.
# Kostet ~400 MB mehr als slim, spart aber Nachbau-Runden.
FROM python:3.12

# Alle System-Libs auf einmal.
RUN apt-get update && apt-get install -y --no-install-recommends \
      ffmpeg \
      libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 \
      libgles2 libegl1 libgomp1 \
      libgtk-3-0 libxkbcommon0 libdbus-1-3 \
      fonts-dejavu fonts-noto fonts-noto-color-emoji \
      curl ca-certificates \
      chromium \
    && rm -rf /var/lib/apt/lists/*
# v101p-fix: System-Chromium fuer den Remotion-Render. Remotion wuerde sich sonst
# zur Laufzeit Chrome von remotion.media ziehen -> auf einem Server mit Egress-
# Allowlist (prod) gibt das 403 und der Motion-Render stirbt. render-brief.mjs
# findet /usr/bin/chromium automatisch (oder via DVE_CHROMIUM).

# v101p: Node 22 for the Remotion motion-graphics engine (motion/). Separate stack;
# the caption pipeline stays pure Python. Cached layer, independent of app code.
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt \
 && pip install --no-cache-dir fastapi uvicorn python-multipart

COPY . /app/

# ONNX-Modelle beim Bauen ziehen (RVM ~30 MB, Depth ~80 MB), damit der
# erste Nutzer nicht wartet.
RUN python -c "import render; render.ensure_models()" || echo "Modelle werden zur Laufzeit geladen"

# v101p: Motion-Engine-Deps + Headless-Browser. KOMPLETT best-effort - der ganze
# Block ist mit `|| echo` abgesichert, sodass ein npm-/Browser-/Netz-Fehler den
# Image-Build NIE kippt. Faellt er aus, erkennt der Server das zur Laufzeit
# (Feature-Detection) und blendet das Motion-Brief-Feature einfach aus; Captions
# + bestehende Motion-Templates laufen davon voellig unberuehrt weiter.
RUN (cd /app/motion && npm ci --no-audit --no-fund) \
    || echo "WARN: Motion-Engine nicht installiert - Brief-Feature bleibt aus"

ENV DVE_DATA=/data DVE_WORKERS=1 DVE_MAX_SECONDS=180 DVE_MAX_MB=300 \
    DVE_CHROMIUM=/usr/bin/chromium
VOLUME /data
EXPOSE 8000
# v98: Docker meldet dem Orchestrator/`docker ps`, ob die App wirklich lebt
HEALTHCHECK --interval=60s --timeout=5s --retries=3 \
  CMD curl -sf http://127.0.0.1:8000/api/health || exit 1
# v98: --proxy-headers + --forwarded-allow-ips: Caddy verbindet aus dem
# Docker-Netz, ohne diese Flags sah uvicorn fuer JEDEN Request die Caddy-IP
# -> alle IP-Rate-Limits (Login, Registrierung, Demo) waren faktisch global.
# '*' ist ok: Port 8000 ist nur im Compose-Netz erreichbar (expose, kein publish).
# WICHTIG: NIE mehrere uvicorn-Worker (--workers) - Queues/Jobs/Rate-Limits
# leben im Prozess-Speicher; Render-Parallelitaet steuert DVE_WORKERS.
CMD ["python", "-m", "uvicorn", "web.server:app", "--host", "0.0.0.0", \
     "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
