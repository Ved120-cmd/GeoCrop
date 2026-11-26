# GeoCrop API image (Railway). Serves geocrop.api.main:app from code + models in git + the runtime data bundle
# (deploy/runtime, built by scripts/deploy/build_data_bundle.py). No raw satellite archives are needed.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    GEOCROP_SCRATCH=/tmp/geocrop/tmp \
    HF_HOME=/tmp/geocrop/hf \
    GEOCROP_PROFILES_ENABLED=0

# libgomp: OpenMP runtime for LightGBM and PyTorch
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements-api.txt .
RUN pip install --extra-index-url https://download.pytorch.org/whl/cpu -r requirements-api.txt

# code, models, AquaCrop engine + FAO crop/soil databases, reference tables
COPY geocrop/ geocrop/
COPY models/ models/
COPY simulator/aquacrop/engine_patched/ simulator/aquacrop/engine_patched/
COPY simulator/aquacrop/gui_ac73/GUI_AC7.3/DATA/ simulator/aquacrop/gui_ac73/GUI_AC7.3/DATA/
COPY simulator/aquacrop/gui_ac73/GUI_AC7.3/SIMUL/ simulator/aquacrop/gui_ac73/GUI_AC7.3/SIMUL/
COPY data/reference/ data/reference/
# runtime data bundle overlays the project tree (data/processed, data/interim/boundaries, IPM PDFs, latest update log)
COPY deploy/runtime/ ./

# run as an unprivileged user; it may write only to data/ (caches) and /tmp
RUN useradd --create-home --uid 10001 app && mkdir -p /tmp/geocrop && chown -R app:app /app/data /tmp/geocrop
USER app

EXPOSE 8000
CMD ["sh", "-c", "uvicorn geocrop.api.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips '*'"]
