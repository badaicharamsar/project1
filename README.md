# Shortest-Path Research Web Application

Localhost research prototype for shortest-path analysis on a user-defined graph using Dijkstra, with optional route ranking using MCDM methods SAW and TOPSIS.

## Project Overview

This project is an academic GIS web application built for local use and presentation. It is designed for:

- opening with an empty workspace centered on Medan,
- importing node-coordinate and edge-analysis data from Excel,
- loading nodes (`simpul`) and edges from JSON, CSV, or Excel-based imports,
- building a directed or undirected weighted graph,
- computing the shortest path with a transparent Dijkstra implementation,
- generating deterministic route alternatives,
- optionally ranking those alternatives using MCDM,
- visualizing results on a Leaflet map and in a dashboard,
- separating the workflow into `Home`, `Shortest Path`, and `Hybrid` menus.

The application is intentionally a research prototype rather than a commercial navigation system. The default route visualization follows the defined graph edges, not a proprietary routing API.

## Feature List

- FastAPI backend with modular services
- HTML, CSS, and vanilla JavaScript frontend
- Leaflet + OpenStreetMap visualization
- Default initial map centered on Medan
- Empty startup workspace with no automatic route execution
- Navigation flow:
  - Home
  - Shortest Path
  - Hybrid
- JSON and CSV support for nodes and edges
- Excel import with Indonesian-style column aliases from research spreadsheets
- Manual add, edit, and delete for nodes and edges
- Directed or undirected graph selection
- Dijkstra optimization by:
  - distance
  - time
  - cost
  - custom combined edge weight
- Deterministic route alternatives via edge-penalty strategy
- Optional MCDM evaluation:
  - SAW
  - TOPSIS
- Result export to:
  - JSON
  - CSV
  - GeoJSON
- Demo dataset auto-loaded on first run
- Presentation-ready dashboard layout for local research demonstrations

## Technology Stack

- Backend: Python + FastAPI
- Frontend: HTML + CSS + vanilla JavaScript
- Map: Leaflet + OpenStreetMap tiles
- Data storage for v1: local files
- Future-ready direction: SQLite can be added behind the service layer later

## Mathematical Concept Summary

### Graph Representation

The transportation or route network is represented as a graph:

- `G = (V, E)`
- `V` is the set of nodes
- `E` is the set of edges

Each node contains:

- `id`
- `name`
- `latitude`
- `longitude`
- optional metadata

Each edge contains:

- `source`
- `target`
- `distance`
- `time`
- `cost`
- `road_condition_score`
- optional metadata

### Dijkstra Shortest Path

For a chosen metric, every edge is assigned a non-negative weight `w(u, v)`. Dijkstra then finds the minimum-cost path from origin to destination.

Core recurrence:

```text
dist(v) = min(dist(v), dist(u) + w(u, v))
```

The algorithm assumes:

- all edge weights are non-negative,
- the graph is finite,
- the chosen optimization metric is well-defined on every traversed edge.

### Why Negative Weights Are Not Allowed

Dijkstra is greedy. Once a node is marked with the current smallest temporary distance, that value is assumed final. Negative weights can violate this assumption, making the result mathematically invalid.

Because of that, the backend rejects negative values for:

- `distance`
- `time`
- `cost`
- computed custom weights

### Custom Combined Edge Weight

The custom metric is defined as:

```text
w_custom = a * distance + b * time + c * cost + d * road_penalty
```

where:

```text
road_penalty = 1 / max(road_condition_score, 0.1)
```

This means better road condition reduces the penalty term.

### Route Alternatives

Alternative routes are generated with a deterministic penalty strategy:

1. Run Dijkstra on the current graph.
2. Penalize edges used by the chosen route.
3. Run Dijkstra again on the penalized graph.
4. Keep unique path sequences only.

This is intentionally simple and transparent for research use.

### SAW

Simple Additive Weighting uses normalized scores and weighted summation.

For a benefit criterion:

```text
r_ij = x_ij / max(x_j)
```

For a cost criterion:

```text
r_ij = min(x_j) / x_ij
```

Final preference:

```text
S_i = sum(w_j * r_ij)
```

### TOPSIS

TOPSIS ranks alternatives by closeness to the ideal positive solution and distance from the ideal negative solution.

1. Decision matrix:

```text
X = [x_ij]
```

2. Vector normalization:

```text
r_ij = x_ij / sqrt(sum(x_ij^2))
```

3. Weighted normalized matrix:

```text
v_ij = w_j * r_ij
```

4. Ideal solutions:

- Benefit criterion:
  - positive ideal = maximum
  - negative ideal = minimum
- Cost criterion:
  - positive ideal = minimum
  - negative ideal = maximum

5. Separation measures:

```text
D_i+ = sqrt(sum((v_ij - v_j+)^2))
D_i- = sqrt(sum((v_ij - v_j-)^2))
```

6. Closeness coefficient:

```text
C_i = D_i- / (D_i+ + D_i-)
```

The preferred route is the one with the highest `C_i`.

## Default Startup Behavior

On first run:

- the map opens centered on Medan,
- the workspace is empty,
- no route is computed automatically,
- the user chooses whether to start from:
  - `Home`
  - `Shortest Path`
  - `Hybrid`

The application is now oriented toward researcher-controlled imports rather than auto-demo execution.

## Folder Structure

```text
project-root/
  backend/
    app/
      main.py
      models.py
      schemas.py
      services/
        graph_service.py
        dijkstra_service.py
        alternatives_service.py
        mcdm_service.py
        file_service.py
      demo_data/
    requirements.txt
  frontend/
    index.html
    styles.css
    app.js
    services.js
    map.js
    ui.js
  README.md
```

## Backend Architecture

- `main.py`: FastAPI app and API endpoints
- `schemas.py`: request and response models
- `models.py`: internal dataclass models for graph operations
- `file_service.py`: JSON/CSV parsing and demo-data loading
- `graph_service.py`: graph validation, graph building, weight resolution
- `dijkstra_service.py`: Dijkstra implementation from scratch
- `alternatives_service.py`: deterministic route alternative generation
- `mcdm_service.py`: SAW and TOPSIS evaluation

The code is structured so a future repository or storage layer can be inserted later for SQLite.

## API Endpoints

- `GET /api/health`
- `GET /api/demo-data`
- `POST /api/data/load`
- `POST /api/graph/build`
- `POST /api/dijkstra/run`
- `POST /api/routes/alternatives`
- `POST /api/mcdm/evaluate`

All endpoints return structured JSON.

## File Format Examples

### Nodes JSON

```json
{
  "nodes": [
    {
      "id": "A",
      "name": "Gerbang Kampus",
      "latitude": -6.973,
      "longitude": 107.63,
      "metadata": {
        "category": "origin"
      },
      "active": true
    }
  ]
}
```

### Edges JSON

```json
{
  "edges": [
    {
      "source": "A",
      "target": "B",
      "distance": 0.35,
      "time": 3.0,
      "cost": 0.0,
      "road_condition_score": 4.0,
      "metadata": {
        "road_name": "Koridor 1"
      }
    }
  ]
}
```

### Nodes CSV

```csv
id,name,latitude,longitude,active,category
A,Gerbang Kampus,-6.973,107.63,true,origin
```

### Edges CSV

```csv
source,target,distance,time,cost,road_condition_score,road_name
A,B,0.35,3,0,4.0,Koridor 1
```

### Accepted Excel Headers from Research Sheets

The Excel importer also accepts Indonesian-style headers such as:

- Nodes / coordinates:
  - `Kode Simpul`
  - `Nama Persimpangan`
  - `Latitude`
  - `Longitude`
- Edges / route data:
  - `Simpul Awal`
  - `Simpul Akhir`
  - `Jarak (km)`
  - `Waktu`
  - optional numeric criteria such as `Lebar`
  - optional identifier fields such as `Kode Sisi`

If `cost` and `road_condition_score` are not present in the imported Excel edge file, the backend assigns defaults:

- `cost = 0`
- `road_condition_score = 3`

## Installation

### 1. Create a Python Virtual Environment

PowerShell:

```powershell
cd C:\Projects\Skripsi-siti
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 2. Install Backend Dependencies

```powershell
pip install -r backend\requirements.txt
```

## How to Run

### Recommended: Run Backend and Frontend Together from FastAPI

From the project root:

```powershell
cd C:\Projects\Skripsi-siti
.venv\Scripts\Activate.ps1
uvicorn backend.app.main:app --reload
```

Then open:

```text
http://127.0.0.1:8000
```

The FastAPI app serves the frontend files directly, so this is the easiest workflow.

### Optional: Serve the Frontend Separately

If you want a separate static frontend server:

1. Start FastAPI on port `8000`.
2. In another terminal:

```powershell
cd C:\Projects\Skripsi-siti\frontend
python -m http.server 5500
```

Then open:

```text
http://127.0.0.1:5500
```

The frontend is configured to call `http://127.0.0.1:8000` automatically when it is not served from port `8000`.

## Deploy to Vercel

This repository is now adapted for Vercel deployment:

- root ASGI entrypoint: `app.py`
- root dependency file: `requirements.txt`
- static frontend build script: `build_public.py`
- Vercel config: `vercel.json`

### What Vercel Will Run

- Python API / FastAPI app from `app.py`
- static frontend files copied from `frontend/` into `public/`

### One-Time Local Check Before Push

```powershell
cd C:\Projects\Skripsi-siti
python build_public.py
```

### Deploy Steps in Vercel Dashboard

1. Import this GitHub repository into Vercel.
2. Keep the project root as the repository root.
3. Confirm that Vercel detects Python.
4. If Vercel asks for a build command, use:

```text
python build_public.py
```

5. If Vercel asks for an output directory for static assets, leave it empty because Vercel will serve `public/` automatically.
6. Deploy.

### Important Notes for Vercel

- The frontend now uses same-origin API calls automatically when deployed online.
- Localhost development still works through FastAPI at `http://127.0.0.1:8000`.
- Vercel is serverless, so do not rely on persistent local file storage on the server.
- Uploaded Excel files are processed per request and are not stored permanently.

## Example Workflow

1. Start the FastAPI server.
2. Open the dashboard in the browser.
3. You will land on `Home` with the map centered on Medan.
4. Open `Shortest Path`.
5. Import one Excel workbook that contains:
   - one route-data sheet
   - one node-coordinate sheet
6. Review the imported graph on the map.
7. Choose origin and destination.
8. Select graph type:
   - directed
   - undirected
9. Select Dijkstra metric:
   - distance
   - time
   - cost
   - custom
10. If using custom metric, edit the coefficients.
11. Click `Run Dijkstra`.
12. Review:
   - highlighted route on the map
   - route sequence
   - total metrics
13. Open `Hybrid` if you want shortest path + MCDM.
14. In `Hybrid`, choose one scenario first.
15. Add criteria from imported numeric fields in the `datafix` sheet or enter manual criteria values per edge alternative.
16. Choose the weight strategy:
   - manual
   - equal
   - stddev
   - CRITIC
17. Run `Hybrid`.
18. Review:
   - edge-level ranking
   - scenario explanation
   - route result
   - normalized matrix or local MCDM steps
19. Export the results to JSON, CSV, or GeoJSON.

## User Interface Summary

- Header: title and session controls
- Left sidebar:
  - dataset upload
  - manual node editor
  - manual edge editor
  - graph and MCDM controls
  - export buttons
- Main panel:
  - Leaflet map
  - nodes, edges, and route layers
- Results panel:
  - chosen path
  - totals
  - route alternatives
  - MCDM tables
  - score bars

## Map Visualization Notes

- Default mode: graph-edge visualization
- Optional mode: road-following placeholder for future integration
- Current placeholder behavior:
  - still draws the route on graph edges
  - warns the user that external routing integration is not active yet

This makes the prototype fully usable without external routing services.

## Export Features

- JSON:
  - dataset
  - graph summary
  - primary route
  - alternatives
  - MCDM result
- CSV:
  - route comparison table
- GeoJSON:
  - nodes
  - edges
  - primary route
  - alternative routes

## Edge Cases Handled

- duplicate node ids
- edges referencing missing nodes
- invalid latitude or longitude
- negative edge values
- disconnected graph
- missing origin or destination
- identical origin and destination
- invalid JSON upload
- invalid CSV structure
- empty or zero-sum MCDM weights

## Notes for Researchers

- The Dijkstra implementation is written from scratch in Python for transparency.
- The route alternative strategy is intentionally simple and deterministic for reproducibility.
- MCDM is optional, so the app can support both:
  - pure shortest-path studies
  - shortest-path + decision-support studies
- The code is intentionally modular and commented so students can extend it.

## Future Improvements

- SQLite storage layer
- import/export project workspace files
- batch experiment execution
- more MCDM methods such as AHP, WP, or ELECTRE
- graph statistics and centrality analysis
- road-following integration with OSRM
- screenshot export or PDF reporting
- sensitivity analysis for criterion weights

## Verification Notes

During development in this workspace:

- Python source files were checked with `python -m compileall backend\app`
- runtime API verification was limited because Python dependencies were not yet installed in the current environment

Install the dependencies and run the server locally to complete end-to-end verification.
