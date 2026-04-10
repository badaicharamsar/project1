from __future__ import annotations

from typing import Any

from ..models import Edge, GraphEdge, Node
from ..schemas import CustomMetricWeights, DatasetSchema, GraphSummarySchema


def _dataset_to_models(dataset: DatasetSchema) -> tuple[dict[str, Node], list[Edge]]:
    node_map: dict[str, Node] = {}
    for node in dataset.nodes:
        if node.id in node_map:
            raise ValueError(f"Duplicate node id found: '{node.id}'.")
        if not -90 <= node.latitude <= 90:
            raise ValueError(f"Latitude for node '{node.id}' must be between -90 and 90.")
        if not -180 <= node.longitude <= 180:
            raise ValueError(f"Longitude for node '{node.id}' must be between -180 and 180.")
        node_map[node.id] = Node(
            id=node.id,
            name=node.name,
            latitude=node.latitude,
            longitude=node.longitude,
            metadata=node.metadata,
            active=node.active,
        )

    edges: list[Edge] = []
    for edge in dataset.edges:
        if edge.source not in node_map or edge.target not in node_map:
            raise ValueError(
                f"Edge '{edge.source} -> {edge.target}' references a node that does not exist."
            )
        for field_name in ("distance", "time", "cost", "road_condition_score"):
            value = getattr(edge, field_name)
            if value < 0:
                raise ValueError(
                    f"Negative value detected on edge '{edge.source} -> {edge.target}' for '{field_name}'. "
                    "Dijkstra requires non-negative edge weights."
                )
        edges.append(
            Edge(
                source=edge.source,
                target=edge.target,
                distance=edge.distance,
                time=edge.time,
                cost=edge.cost,
                road_condition_score=edge.road_condition_score,
                metadata=edge.metadata,
            )
        )
    return node_map, edges


def _collect_dataset_warnings(edges: list[Edge], active_node_ids: set[str] | None = None) -> list[str]:
    warnings: list[str] = []

    missing_distance_edges = [
        f"{edge.source}->{edge.target}"
        for edge in edges
        if edge.metadata.get("_missing_distance")
        and (not active_node_ids or (edge.source in active_node_ids and edge.target in active_node_ids))
    ]
    if missing_distance_edges:
        warnings.append(
            "Jarak belum ada pada file, coba input manual. "
            f"Edge terkait: {', '.join(missing_distance_edges[:10])}."
        )

    return warnings


def summarize_dataset(
    dataset: DatasetSchema,
    graph_type: str = "undirected",
    active_node_ids: list[str] | None = None,
    metric: str = "distance",
) -> GraphSummarySchema:
    node_map, edges = _dataset_to_models(dataset)
    if not node_map:
        raise ValueError("Dataset must contain at least one node.")
    if not edges:
        raise ValueError("Dataset must contain at least one edge.")

    requested_node_ids = set(active_node_ids or [])
    if requested_node_ids:
        missing = requested_node_ids - set(node_map.keys())
        if missing:
            raise ValueError(f"Active node ids not found in dataset: {sorted(missing)}.")
        active_nodes = {
            node_id: node for node_id, node in node_map.items() if node_id in requested_node_ids
        }
    else:
        active_nodes = {node_id: node for node_id, node in node_map.items() if node.active}

    isolated_nodes = []
    connected_ids: set[str] = set()
    for edge in edges:
        if edge.source in active_nodes and edge.target in active_nodes:
            connected_ids.add(edge.source)
            connected_ids.add(edge.target)

    isolated_nodes = [node_id for node_id in active_nodes if node_id not in connected_ids]
    warnings = _collect_dataset_warnings(edges, set(active_nodes.keys()))
    if isolated_nodes:
        warnings.append(
            "Some active nodes are isolated and cannot be part of any route: "
            + ", ".join(isolated_nodes)
            + "."
        )

    graph_edge_count = sum(
        2 if graph_type == "undirected" else 1
        for edge in edges
        if edge.source in active_nodes and edge.target in active_nodes
    )

    return GraphSummarySchema(
        graph_type=graph_type,
        metric=metric,
        node_count=len(node_map),
        active_node_count=len(active_nodes),
        original_edge_count=len(edges),
        graph_edge_count=graph_edge_count,
        isolated_nodes=isolated_nodes,
        warnings=warnings,
    )


def resolve_weight(
    edge: Edge,
    metric: str,
    custom_metric_weights: CustomMetricWeights | None = None,
) -> float:
    """Translate edge attributes into a single non-negative Dijkstra weight."""

    if metric == "distance":
        if edge.metadata.get("_missing_distance"):
            raise ValueError("Jarak belum ada pada file, coba input manual.")
        return edge.distance
    if metric == "time":
        return edge.time
    if metric == "cost":
        return edge.cost
    if metric != "custom":
        raise ValueError(f"Unsupported metric: {metric}.")

    weights = custom_metric_weights or CustomMetricWeights()
    if all(value == 0 for value in weights.model_dump().values()):
        raise ValueError("Custom metric weights cannot all be zero.")
    if edge.metadata.get("_missing_distance") and weights.distance > 0:
        raise ValueError("Jarak belum ada pada file, coba input manual.")

    # Road condition is a benefit criterion: better roads should reduce the route penalty.
    road_penalty = 1.0 / max(edge.road_condition_score, 0.1)
    combined_weight = (
        weights.distance * edge.distance
        + weights.time * edge.time
        + weights.cost * edge.cost
        + weights.road_condition * road_penalty
    )
    if combined_weight < 0:
        raise ValueError("Custom combined weight must remain non-negative.")
    return combined_weight


def build_graph(
    dataset: DatasetSchema,
    graph_type: str = "undirected",
    metric: str = "distance",
    active_node_ids: list[str] | None = None,
    custom_metric_weights: CustomMetricWeights | None = None,
    edge_weight_overrides: dict[tuple[str, str], float] | None = None,
) -> dict[str, Any]:
    summary = summarize_dataset(
        dataset=dataset,
        graph_type=graph_type,
        active_node_ids=active_node_ids,
        metric=metric,
    )
    node_map, edges = _dataset_to_models(dataset)
    requested_node_ids = set(active_node_ids or [])
    active_nodes = (
        {node_id: node for node_id, node in node_map.items() if node_id in requested_node_ids}
        if requested_node_ids
        else {node_id: node for node_id, node in node_map.items() if node.active}
    )

    if len(active_nodes) < 2:
        raise ValueError("At least two active nodes are required to build a usable graph.")

    adjacency: dict[str, list[GraphEdge]] = {node_id: [] for node_id in active_nodes}
    used_edges = 0

    for edge in edges:
        if edge.source not in active_nodes or edge.target not in active_nodes:
            continue

        override_weight = None
        if edge_weight_overrides:
            override_weight = edge_weight_overrides.get((edge.source, edge.target))
            if override_weight is None and graph_type == "undirected":
                override_weight = edge_weight_overrides.get((edge.target, edge.source))

        computed_weight = (
            override_weight
            if override_weight is not None
            else resolve_weight(edge, metric, custom_metric_weights)
        )
        if computed_weight < 0:
            raise ValueError(
                f"Negative computed weight found for edge '{edge.source} -> {edge.target}'."
            )

        adjacency[edge.source].append(
            GraphEdge(
                source=edge.source,
                target=edge.target,
                distance=edge.distance,
                time=edge.time,
                cost=edge.cost,
                road_condition_score=edge.road_condition_score,
                computed_weight=computed_weight,
                metadata=edge.metadata,
            )
        )
        used_edges += 1

        if graph_type == "undirected":
            adjacency[edge.target].append(
                GraphEdge(
                    source=edge.target,
                    target=edge.source,
                    distance=edge.distance,
                    time=edge.time,
                    cost=edge.cost,
                    road_condition_score=edge.road_condition_score,
                    computed_weight=computed_weight,
                    metadata=edge.metadata,
                )
            )
            used_edges += 1

    summary = summary.model_copy(update={"graph_edge_count": used_edges})
    return {
        "nodes": active_nodes,
        "adjacency": adjacency,
        "summary": summary,
        "graph_type": graph_type,
        "metric": metric,
    }
