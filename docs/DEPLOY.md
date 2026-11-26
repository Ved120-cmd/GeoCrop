# Deploying GeoCrop: API on Railway, web app on Render

```
Browser ──> Render static site (frontend/dist) ──HTTPS──> Railway API (Docker, geocrop.api.main:app)
```

**Profiles are off online:** `GEOCROP_PROFILES_ENABLED=0` and `VITE_PROFILES_ENABLED=false`. There is no login yet, so the public site collects no personal data and needs no database.

## What goes into the API image
- **From git:** code, models, the AquaCrop engine with the FAO crop/soil files, and `data/reference`.
- **The runtime data bundle `deploy/runtime/` (about 98 MB, committed):** Monitor series and indices, weather, Predict forecasts, soil tables, Crop Advisor runs, district boundaries, the eight NIPHM IPM PDFs, and the latest update log. It's built by `scripts/deploy/build_data_bundle.py` from the local data. The multi-GB raw archives aren't needed.
- **PyTorch** is the CPU build; the container runs as a non-root user.

**Verified before deploying:** the image's file set was staged on D: and every public endpoint answered with no `.env` and no database. That included a Plant Doctor diagnosis and a simulator run.

## One-time setup
1. **Railway (API)**
   1. New Project → Deploy from GitHub repo → `Ved120-cmd/GeoCrop`. Railway reads `railway.json` and builds the `Dockerfile`.
   2. Settings → Networking → **Generate Domain** (for example `geocrop-api-production.up.railway.app`).
   3. Variables:
      * `GEOCROP_ALLOWED_ORIGINS` = the Render URL from step 2, for example `https://geocrop-web.onrender.com`. Comma-separate several.
      * `GEOCROP_PROFILES_ENABLED` = `0`. This is already the image default.
   4. Memory: Plant Doctor loads PyTorch and the model on first use, about 0.8–1 GB. Pick a plan with at least 1 GB of RAM.
2. **Render (web app)**
   1. New → Blueprint → the same repo. Render reads `render.yaml`.
   2. Set `VITE_API_BASE` = `https://<your-railway-domain>`, with no trailing slash.
   3. After the first deploy, copy the site URL into Railway's `GEOCROP_ALLOWED_ORIGINS`. Railway redeploys automatically.
3. **Check:**
   * open `https://<railway-domain>/health` (should show `{"status":"ok"}`) and `/features` (should show `{"profiles":false}`);
   * open the Render URL and visit every page;
   * run a Plant Doctor diagnosis. The first one takes about 20 s while the model loads.

## Updating data (the site shows a frozen snapshot)
Railway doesn't run the daily data update: it needs Earth Engine credentials and the raw archives. To refresh:

```bash
.venv/Scripts/python -m geocrop.monitor.update          # local, ~10-15 min
.venv/Scripts/python scripts/deploy/build_data_bundle.py
git add deploy/runtime && git commit -m "Refresh deployed data" && git push   # Railway rebuilds
```

## Turning profiles on later
This needs real authentication first (for example phone OTP) plus rate limiting (see docs/SECURITY.md). Then:
1. Add a Railway PostgreSQL service; Railway provides `DATABASE_URL`.
2. Set `GEOCROP_PROFILES_ENABLED=1` on Railway and `VITE_PROFILES_ENABLED=true` on Render.
3. Run `python -m geocrop.db` once to create the tables.

## Notes
* **CORS/CSRF:** write requests from the site carry `X-GeoCrop-Client: web`, and their Origin must be listed in `GEOCROP_ALLOWED_ORIGINS`.
* **Memory:** the simulator writes run folders under `/tmp/geocrop` and keeps up to 10 engine processes per request, so watch memory on small plans.
