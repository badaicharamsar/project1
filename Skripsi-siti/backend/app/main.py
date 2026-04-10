from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .schemas import (
    AlternativesRequest,
    AlternativesResponse,
    DijkstraRequest,
    DijkstraResponse,
    GraphBuildRequest,
    GraphSummarySchema,
    HybridRequest,
    HybridResponse,
    LoadDataRequest,
    LoadDataResponse,
    McdmRequest,
    McdmResponse,
)
from .services.alternatives_service import generate_alternative_routes
from .services.dijkstra_service import run_dijkstra
from .services.file_service import (
    load_demo_dataset,
    resolve_dataset,
    resolve_excel_dataset,
    resolve_single_workbook_dataset,
)
from .services.graph_service import build_graph, summarize_dataset
from .services.hybrid_service import run_hybrid_analysis
from .services.mcdm_service import evaluate_routes

ROOT_DIR = Path(__file__).resolve().parents[2]
FRONTEND_DIR = ROOT_DIR / "frontend"
DEMO_DIR = Path(__file__).resolve().parent / "demo_data"

app = FastAPI(
    title="Shortest Path Research Prototype",
    description="Local academic web application for Dijkstra and optional MCDM route analysis.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def _graph_summary_from_dataset(dataset, graph_type: str = "undirected", metric: str = "distance") -> GraphSummarySchema:
    return summarize_dataset(dataset=dataset, graph_type=graph_type, metric=metric)


@app.get("/", include_in_schema=False)
async def serve_frontend() -> FileResponse:
    index_path = FRONTEND_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="Frontend index.html was not found.")
    return FileResponse(index_path)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "message": "Shortest-path research prototype is running."}


@app.get("/api/demo-data", response_model=LoadDataResponse)
async def get_demo_data() -> LoadDataResponse:
    try:
        dataset = load_demo_dataset(DEMO_DIR)
        summary = _graph_summary_from_dataset(dataset)
        return LoadDataResponse(dataset=dataset, summary=summary)
    except Exception as exc:  # pragma: no cover - defensive startup path
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/data/load", response_model=LoadDataResponse)
async def load_data(request: LoadDataRequest) -> LoadDataResponse:
    try:
        dataset = resolve_dataset(request)
        summary = _graph_summary_from_dataset(dataset)
        return LoadDataResponse(dataset=dataset, summary=summary)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/data/upload-excel", response_model=LoadDataResponse)
async def upload_excel_data(
    nodes_file: UploadFile = File(...),
    edges_file: UploadFile = File(...),
) -> LoadDataResponse:
    try:
        dataset = resolve_excel_dataset(
            nodes_content=await nodes_file.read(),
            edges_content=await edges_file.read(),
        )
        summary = _graph_summary_from_dataset(dataset)
        return LoadDataResponse(dataset=dataset, summary=summary)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/data/upload-workbook", response_model=LoadDataResponse)
async def upload_single_workbook(workbook_file: UploadFile = File(...)) -> LoadDataResponse:
    try:
        dataset = resolve_single_workbook_dataset(await workbook_file.read())
        summary = _graph_summary_from_dataset(dataset)
        return LoadDataResponse(dataset=dataset, summary=summary)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/graph/build", response_model=GraphSummarySchema)
async def graph_build(request: GraphBuildRequest) -> GraphSummarySchema:
    try:
        graph_bundle = build_graph(
            dataset=request.dataset,
            graph_type=request.graph_type,
            metric=request.metric,
            active_node_ids=request.active_node_ids,
            custom_metric_weights=request.custom_metric_weights,
        )
        return graph_bundle["summary"]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/dijkstra/run", response_model=DijkstraResponse)
async def dijkstra_run(request: DijkstraRequest) -> DijkstraResponse:
    try:
        graph_bundle = build_graph(
            dataset=request.dataset,
            graph_type=request.graph_type,
            metric=request.metric,
            active_node_ids=request.active_node_ids,
            custom_metric_weights=request.custom_metric_weights,
        )
        result = run_dijkstra(graph_bundle, request.origin_id, request.destination_id)
        return DijkstraResponse(summary=graph_bundle["summary"], result=result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/routes/alternatives", response_model=AlternativesResponse)
async def route_alternatives(request: AlternativesRequest) -> AlternativesResponse:
    try:
        graph_bundle = build_graph(
            dataset=request.dataset,
            graph_type=request.graph_type,
            metric=request.metric,
            active_node_ids=request.active_node_ids,
            custom_metric_weights=request.custom_metric_weights,
        )
        alternatives = generate_alternative_routes(
            graph_bundle=graph_bundle,
            origin_id=request.origin_id,
            destination_id=request.destination_id,
            max_routes=request.max_routes,
            penalty_factor=request.penalty_factor,
        )
        return AlternativesResponse(summary=graph_bundle["summary"], alternatives=alternatives)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/mcdm/evaluate", response_model=McdmResponse)
async def mcdm_evaluate(request: McdmRequest) -> McdmResponse:
    try:
        result = evaluate_routes(
            alternatives=[alternative.model_dump() for alternative in request.alternatives],
            criteria=request.criteria,
            method=request.method,
        )
        return McdmResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/hybrid/run", response_model=HybridResponse)
async def hybrid_run(request: HybridRequest) -> HybridResponse:
    try:
        result = run_hybrid_analysis(
            dataset=request.dataset,
            origin_id=request.origin_id,
            destination_id=request.destination_id,
            graph_type=request.graph_type,
            criteria_payload=[criterion.model_dump() for criterion in request.criteria],
            mcdm_method=request.method,
            weight_method=request.weight_method,
            scenario=request.scenario,
            active_node_ids=request.active_node_ids,
        )
        return HybridResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/{asset_path:path}", include_in_schema=False)
async def serve_frontend_asset(asset_path: str) -> FileResponse:
    file_path = FRONTEND_DIR / asset_path
    if file_path.exists() and file_path.is_file():
        return FileResponse(file_path)
    raise HTTPException(status_code=404, detail="Frontend asset was not found.")
