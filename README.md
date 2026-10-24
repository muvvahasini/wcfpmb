# WindLens

WindLens is a day-ahead decision-support dashboard for national GB wind generation. It shows the latest Elexon wind forecast available by a selected decision cutoff and compares forecasts with actual generation to quantify forecast accuracy.

The application is scoped to purchase decisions made from 1–31 January 2026, corresponding to delivery dates 2 January–1 February 2026. It uses Elexon FUELHH actuals filtered to `fuelType=WIND` and WINDFOR forecasts only. It does not calculate demand, total power requirements, or a procurement quantity.

## Project structure

```text
repository/
├── README.md
└── windlens/                         # Application root
    ├── frontend/                     # React + Vite UI (Vercel frontend root)
    │   ├── src/
    │   │   ├── App.jsx               # Dashboard, charts, and user workflow
    │   │   ├── api.js                # Backend API client
    │   │   ├── main.jsx              # React entry point
    │   │   └── styles.css
    │   ├── package.json
    │   └── vite.config.js            # Local API proxy
    ├── backend/                      # FastAPI service (Vercel backend root)
    │   ├── app/
    │   │   ├── main.py               # API endpoints and data loading
    │   │   ├── services/             # Forecast selection and metrics
    │   │   └── utils/                # UTC and UK timezone helpers
    │   ├── data/processed/           # Processed CSVs bundled with backend
    │   ├── tests/                    # Backend tests
    │   └── requirements.txt
    ├── scripts/
    │   ├── ingest.py                 # Download Elexon FUELHH and WINDFOR
    │   └── process_data.py           # Validate, clean, report, sync backend data
    ├── data/                         # Raw and local processed CSVs
    ├── Dockerfile                    # Combined frontend/backend image
    ├── docker-compose.yml            # Local Docker configuration
    ├── heroku.yml                    # Heroku container configuration
    ├── requirements.txt              # Root-level Python dependencies
    └── .gitignore
```

The ingestion and processing scripts are data-maintenance tools, not runtime services. Run them from `windlens/` (the application root) when refreshing Elexon data. They write raw and local processed data under `windlens/data/` and synchronize deployment-ready files to `windlens/backend/data/processed/`. The Vercel frontend project uses `windlens/frontend/`; the backend project uses `windlens/backend/`.

## Client use case

The intended user is a UK utility's day-ahead electricity buying team. Before a delivery day, the user selects the delivery date and the time by which the buying decision must be made. WindLens shows the latest Elexon national wind forecast available by that cutoff, when it was published, and how it compares with actual wind generation for historical validation.

The app helps the team understand the wind forecast and its historical error when considering a purchase. It does not calculate consumer demand, total supply, a system shortfall, or a recommended purchase amount: those require demand and other supply data, which are explicitly outside this product's data scope.

### User workflow

1. Open WindLens and choose a delivery day in the supported date range. These dates correspond to purchase decisions made during January 2026.
2. Set the decision cutoff in UK local time. The default is 09:20 on the day before delivery; confirm this assumption against the team's actual trading deadline.
3. Review the daily wind forecast and the actual-generation comparison. The publication time shown is the selected forecast version available by the cutoff.
4. Review daily forecast error measures (MAE, RMSE, and bias), plus the historical accuracy charts. Error is forecast minus actual; positive bias means wind was over-forecast.
5. Select a chart point or detail-table row to inspect the forecast versions for that delivery hour, including which version was selected and which were published too late.
6. Use these forecast and historical-error measures as decision support alongside the team's other systems and information. Do not interpret WindLens as a total procurement recommendation.

## End-to-end data and application pipeline

```text
Elexon FUELHH stream                 Elexon WINDFOR stream
  actual generation                     forecast versions
  filter fuelType=WIND                  startTime, publishTime, generation
           \                                  /
            \                                /
             scripts/ingest.py (date chunks, retries)
                              |
                    raw data/actuals.csv
                    raw data/forecasts.csv
                              |
                    scripts/process_data.py
       validate -> remove duplicates/conflicts -> flag/remove heuristic outliers
                              |
     data/processed/actuals.csv, forecasts.csv, quality report, flagged rows
                              |
        FastAPI loads and parses data as UTC-aware timestamps
                              |
     select latest forecast published by previous-day UK cutoff
                              |
   aggregate complete pairs of half-hour actuals into UTC hourly actuals
                              |
            match forecasts and actuals by delivery hour
                              |
             calculate errors and accuracy metrics
                              |
          React dashboard requests and presents API results
```

### Pipeline stages

1. **Ingestion:** `scripts/ingest.py` calls the Elexon FUELHH and WINDFOR stream endpoints. It requests actuals in seven-day chunks and forecasts in two-day chunks, retries failed requests, filters FUELHH to wind, and writes the raw CSV files under `data/`. It then runs the processing script.
2. **Data quality processing:** `scripts/process_data.py` checks required fields, timestamps, and numeric/non-negative generation values; keeps WIND actuals; removes exact duplicate records and all records in conflicting duplicate-key groups; and applies a rolling-MAD outlier heuristic. It preserves the raw CSVs, writes cleaned CSVs to `data/processed/`, saves flagged rows separately, and writes `processing_report.json`. Outlier detection is heuristic and can flag legitimate rapid changes.
3. **Backend loading and decision-time selection:** FastAPI loads the processed CSVs and normalizes timestamps to UTC. For each delivery hour, it identifies the delivery date in UK time, calculates the previous-day cutoff (including UK daylight-saving time), filters out forecasts published after that cutoff, and chooses the latest eligible `publishTime`.
4. **Actual/forecast alignment:** WINDFOR values are hourly; FUELHH values are half-hourly. The backend averages the two actual readings in each UTC hour and excludes an hour if either reading is missing. It matches the resulting hourly actual with the selected forecast by timestamp; it does not fill missing values with zero.
5. **Metrics and API:** The backend calculates signed error (`forecast - actual`), absolute error, MAE, RMSE, bias, percentile miss, and MAPE (excluding actuals at or below 100 MW). The API provides metadata, delivery-day, forecast-history, and accuracy endpoints. Day and accuracy requests are limited to delivery dates associated with January 2026 decisions.
6. **Frontend presentation:** React calls the API, displays the chosen forecast and comparison charts/KPIs, and provides forecast-version history and interval detail. The frontend is served by FastAPI in the Docker image; in local development, Vite proxies `/api` to the backend.
7. **Runtime packaging:** Docker builds the React app, installs the Python backend dependencies, processes the included raw CSVs during image build, and runs FastAPI to serve both the API and static frontend. For Vercel, the README's deployment option hosts the frontend there and requires the API to be separately reachable and configured with the Vercel origin in CORS.

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
