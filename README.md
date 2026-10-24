# WindLens

WindLens is a day-ahead decision-support dashboard for national GB wind generation. It shows the latest Elexon wind forecast available by a selected decision cutoff and compares forecasts with actual generation to quantify forecast accuracy.

The application is scoped to purchase decisions made from 1–31 January 2026, corresponding to delivery dates 2 January–1 February 2026. It uses Elexon FUELHH actuals filtered to `fuelType=WIND` and WINDFOR forecasts only. It does not calculate demand, total power requirements, or a procurement quantity.

## Project structure

- `frontend/` — React, Vite, and Recharts dashboard
- `backend/app/` — Python FastAPI API and forecast/accuracy logic
- `scripts/ingest.py` — downloads Elexon FUELHH and WINDFOR CSVs
- `scripts/process_data.py` — validates and cleans the CSVs, preserving raw files and writing cleaned files and a quality report under `data/processed/`
- `backend/tests/` — backend tests
- `Dockerfile` and `docker-compose.yml` — build and run the frontend and backend together in one container

## Run with Docker

### Prerequisites

- Install and start Docker Desktop (Windows/macOS) or Docker Engine with the Compose plugin (Linux).
- From a terminal, change to the project directory containing `docker-compose.yml`.

### Start the application

```powershell
docker compose up --build
```

The first build installs dependencies, builds the React frontend, processes the CSV files in `data/`, and starts the FastAPI server. Open [http://localhost:8000](http://localhost:8000) in a browser.

To stop the application, press **Ctrl+C** in the terminal. To run it in the background instead:

```powershell
docker compose up --build -d
```

Then stop the background containers with:

```powershell
docker compose down
```

If you replace or re-ingest the CSV files, rebuild the image so the updated data is included:

```powershell
docker compose up --build
```

### Refresh the CSV data (optional)

Ingestion requires internet access and Python dependencies on the host:

```powershell
python -m pip install -r backend\requirements.txt
python scripts\ingest.py 2025-12-31 2026-02-02
```

The ingestion script downloads raw CSVs into `data/` and then runs the processing script. The Docker image processes the CSVs again during its build and serves the cleaned versions.

## Deploy the frontend with Vercel

The repository's Dockerfile runs **both** the React frontend and FastAPI backend as one container. A standard Vercel Vite deployment hosts the frontend; it does not run this Dockerfile as a combined container. Deploy the FastAPI backend to a host that can run Docker or Python, or adapt the backend to Vercel's Python Functions before deploying the whole API there.

For the frontend-on-Vercel option:

1. Push the project to your Git provider and import that repository into Vercel.
2. Set **Root Directory** to `frontend`.
3. Select **Vite** as the framework preset. Use `npm run build` as the build command and `dist` as the output directory.
4. Add the `VITE_API_URL` environment variable with the public origin of the deployed FastAPI backend, for example `https://your-api.example.com` (no trailing slash). Do not use `localhost` for a deployed frontend.
5. Configure the backend's `CORS_ORIGINS` environment variable to include the exact deployed Vercel frontend origin, such as `https://your-project.vercel.app`.
6. Deploy or redeploy the frontend after setting environment variables. Verify that the site loads and that `/api/metadata` requests succeed.

The backend needs the processed CSVs at runtime. For a Docker-hosted backend, build the project Dockerfile so it includes and processes `data/`. Ensure the backend host has persistent/available data files if you deploy it using a different method.

## Run locally without Docker

From the project root, install backend dependencies and ensure the CSVs have been ingested and processed. Then start the backend and frontend in separate terminals.

Backend (PowerShell):

```powershell
Set-Location backend
$env:PYTHONPATH = "."
python -m uvicorn app.main:app --reload --port 8000
```

Frontend (PowerShell):

```powershell
Set-Location frontend
npm install
npm run dev
```

Open the Vite URL shown in the frontend terminal (usually [http://localhost:5173](http://localhost:5173)). Vite proxies `/api` requests to the local backend at `http://localhost:8000`.

## Method and assumptions

- The default decision cutoff is 09:20 UK time on the day before delivery; it can be adjusted in the UI. Confirm the cutoff against the trading team's actual deadline.
- For each delivery hour, the app selects the latest WINDFOR forecast published at or before the selected cutoff on the previous UK calendar day.
- WINDFOR forecasts are hourly while FUELHH actuals are half-hourly. The two actual readings in a UTC hour are averaged to align them with the hourly forecast. Incomplete actual hours are excluded from accuracy calculations.
- Error is forecast minus actual. Positive bias means over-forecasting; negative bias means under-forecasting. Metrics use only intervals with both a selected forecast and a complete actual.
- Potential outliers are handled by the rolling-MAD rule documented in `data/processed/processing_report.json`; flagged rows are saved for review. This is a heuristic and can flag genuine rapid changes.
- Only Elexon national wind data is used. Without demand and other supply data, the app cannot calculate total power requirements or recommend the amount to procure.

## Tests

From the `backend` directory:

```powershell
$env:PYTHONPATH = "."
python -m pytest -q
```

Build the frontend from the `frontend` directory:

```powershell
npm run build
```

## AI disclosure

Built with AI assistance (planning, code, tests, and documentation)
