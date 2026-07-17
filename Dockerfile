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
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt \
 && pip install --no-cache-dir fastapi uvicorn python-multipart

COPY . /app/

# ONNX-Modelle beim Bauen ziehen (RVM ~30 MB, Depth ~80 MB), damit der
# erste Nutzer nicht wartet.
RUN python -c "import render; render.ensure_models()" || echo "Modelle werden zur Laufzeit geladen"

ENV DVE_DATA=/data DVE_WORKERS=1 DVE_MAX_SECONDS=180 DVE_MAX_MB=300
VOLUME /data
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "web.server:app", "--host", "0.0.0.0", "--port", "8000"]
