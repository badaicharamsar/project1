from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


MetricName = Literal["distance", "time", "cost", "custom"]
GraphType = Literal["directed", "undirected"]
McdmMethod = Literal["saw", "topsis"]
CriterionKind = Literal["benefit", "cost"]
SourceFormat = Literal["json", "csv"]
WeightMethod = Literal["manual", "equal", "stddev", "critic"]
HybridScenario = Literal["scenario_1", "scenario_2"]


class NodeSchema(BaseModel):
    id: str = Field(..., description="Unique node identifier.")
    name: str = Field(..., description="Human-readable node name.")
    latitude: float
    longitude: float
    metadata: dict[str, Any] = Field(default_factory=dict)
    active: bool = True


class EdgeSchema(BaseModel):
    source: str
    target: str
    distance: float = Field(..., ge=0)
    time: float = Field(..., ge=0)
    cost: float = Field(..., ge=0)
    road_condition_score: float = Field(..., ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DatasetSchema(BaseModel):
    nodes: list[NodeSchema] = Field(default_factory=list)
    edges: list[EdgeSchema] = Field(default_factory=list)


class TextDataSource(BaseModel):
    format: SourceFormat
    content: str


class LoadDataRequest(BaseModel):
    dataset: DatasetSchema | None = None
    nodes_source: TextDataSource | None = None
    edges_source: TextDataSource | None = None


class CustomMetricWeights(BaseModel):
    distance: float = Field(1.0, ge=0)
    time: float = Field(0.0, ge=0)
    cost: float = Field(0.0, ge=0)
    road_condition: float = Field(0.0, ge=0)


class GraphBuildRequest(BaseModel):
    dataset: DatasetSchema
    graph_type: GraphType = "undirected"
    metric: MetricName = "distance"
    active_node_ids: list[str] | None = None
    custom_metric_weights: CustomMetricWeights | None = None


class DijkstraRequest(GraphBuildRequest):
    origin_id: str
    destination_id: str


class AlternativesRequest(DijkstraRequest):
    max_routes: int = Field(3, ge=1, le=10)
    penalty_factor: float = Field(1.35, ge=1.0, le=10.0)


class TraversedEdgeSchema(BaseModel):
    source: str
    target: str
    distance: float
    time: float
    cost: float
    road_condition_score: float
    optimized_weight: float


class RouteResultSchema(BaseModel):
    route_id: str
    path_nodes: list[str]
    path_names: list[str]
    traversed_edges: list[TraversedEdgeSchema]
    total_distance: float
    total_time: float
    total_cost: float
    average_road_condition: float
    hops: int
    optimized_weight: float
    extra_metrics: dict[str, float] = Field(default_factory=dict)


class CriterionSchema(BaseModel):
    field: str = Field(..., description="Route attribute, e.g. total_distance.")
    label: str = Field(..., description="Readable criterion name.")
    kind: CriterionKind
    weight: float = Field(..., ge=0)


class McdmRequest(BaseModel):
    method: McdmMethod
    criteria: list[CriterionSchema]
    alternatives: list[RouteResultSchema]


class HybridCriterionSchema(BaseModel):
    criterion_id: str
    field: str
    label: str
    kind: CriterionKind
    weight: float = Field(0.0, ge=0)
    manual_values: dict[str, float] = Field(default_factory=dict)


class HybridRequest(BaseModel):
    dataset: DatasetSchema
    origin_id: str
    destination_id: str
    graph_type: GraphType = "undirected"
    active_node_ids: list[str] | None = None
    scenario: HybridScenario
    method: McdmMethod
    weight_method: WeightMethod
    criteria: list[HybridCriterionSchema]


class GraphSummarySchema(BaseModel):
    graph_type: GraphType
    metric: MetricName
    node_count: int
    active_node_count: int
    original_edge_count: int
    graph_edge_count: int
    isolated_nodes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class LoadDataResponse(BaseModel):
    dataset: DatasetSchema
    summary: GraphSummarySchema


class DijkstraResponse(BaseModel):
    summary: GraphSummarySchema
    result: RouteResultSchema


class AlternativesResponse(BaseModel):
    summary: GraphSummarySchema
    alternatives: list[RouteResultSchema]


class McdmResultRow(BaseModel):
    route_id: str
    score: float
    rank: int


class McdmResponse(BaseModel):
    method: McdmMethod
    criteria: list[CriterionSchema]
    decision_matrix: list[dict[str, Any]]
    normalized_matrix: list[dict[str, Any]]
    weighted_matrix: list[dict[str, Any]]
    ranking: list[McdmResultRow]
    explanation: str


class HybridResponse(BaseModel):
    scenario: HybridScenario
    method: McdmMethod
    weight_method: WeightMethod
    criteria: list[dict[str, Any]]
    weights_table: list[dict[str, Any]]
    edge_alternatives: list[dict[str, Any]]
    decision_matrix: list[dict[str, Any]]
    normalized_matrix: list[dict[str, Any]]
    weighted_matrix: list[dict[str, Any]]
    ranking: list[dict[str, Any]]
    route_result: RouteResultSchema
    local_steps: list[dict[str, Any]]
    explanation: str
