from __future__ import annotations

import heapq
import math
import re
from typing import Any

from ..models import GraphEdge


def _slugify(value: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "_", value.strip().lower())
    return text.strip("_")


def _compute_extra_metrics(traversed_edges: list[GraphEdge]) -> dict[str, float]:
    numeric_columns: dict[str, list[float]] = {}

    for edge in traversed_edges:
        for key, value in edge.metadata.items():
            if isinstance(value, bool):
                continue
            if isinstance(value, (int, float)):
                numeric_columns.setdefault(f"avg_{_slugify(key)}", []).append(float(value))

    return {
        metric_name: round(sum(values) / len(values), 6)
        for metric_name, values in numeric_columns.items()
        if values
    }


def assemble_route_result(
    nodes: dict[str, Any],
    ordered_nodes: list[str],
    traversed_edges: list[GraphEdge],
    route_id: str = "R1",
    optimized_weight: float | None = None,
) -> dict[str, Any]:
    total_distance = sum(edge.distance for edge in traversed_edges)
    total_time = sum(edge.time for edge in traversed_edges)
    total_cost = sum(edge.cost for edge in traversed_edges)
    average_road_condition = (
        sum(edge.road_condition_score for edge in traversed_edges) / len(traversed_edges)
        if traversed_edges
        else 0.0
    )
    extra_metrics = _compute_extra_metrics(traversed_edges)

    return {
        "route_id": route_id,
        "path_nodes": ordered_nodes,
        "path_names": [nodes[node_id].name for node_id in ordered_nodes],
        "traversed_edges": [
            {
                "source": edge.source,
                "target": edge.target,
                "distance": round(edge.distance, 4),
                "time": round(edge.time, 4),
                "cost": round(edge.cost, 4),
                "road_condition_score": round(edge.road_condition_score, 4),
                "optimized_weight": round(edge.computed_weight, 6),
            }
            for edge in traversed_edges
        ],
        "total_distance": round(total_distance, 4),
        "total_time": round(total_time, 4),
        "total_cost": round(total_cost, 4),
        "average_road_condition": round(average_road_condition, 4),
        "hops": len(traversed_edges),
        "optimized_weight": round(
            optimized_weight if optimized_weight is not None else sum(edge.computed_weight for edge in traversed_edges),
            6,
        ),
        "extra_metrics": extra_metrics,
    }


def run_dijkstra(
    graph_bundle: dict[str, Any],
    origin_id: str,
    destination_id: str,
    penalty_lookup: dict[tuple[str, str], int] | None = None,
    penalty_factor: float = 1.0,
    route_id: str = "R1",
) -> dict[str, Any]:
    """Run Dijkstra on an adjacency-list graph using non-negative edge weights."""

    adjacency: dict[str, list[GraphEdge]] = graph_bundle["adjacency"]
    nodes = graph_bundle["nodes"]

    if origin_id not in adjacency:
        raise ValueError(f"Origin node '{origin_id}' is not active in the current graph.")
    if destination_id not in adjacency:
        raise ValueError(f"Destination node '{destination_id}' is not active in the current graph.")

    distances = {node_id: math.inf for node_id in adjacency}
    previous: dict[str, tuple[str, GraphEdge] | None] = {node_id: None for node_id in adjacency}
    distances[origin_id] = 0.0

    queue: list[tuple[float, int, str]] = [(0.0, 0, origin_id)]
    step_counter = 0

    while queue:
        current_distance, _, current_node = heapq.heappop(queue)
        if current_distance > distances[current_node]:
            continue
        if current_node == destination_id:
            break

        for edge in sorted(adjacency[current_node], key=lambda item: (item.computed_weight, item.target)):
            penalty_count = penalty_lookup.get((edge.source, edge.target), 0) if penalty_lookup else 0
            penalized_weight = edge.computed_weight * (penalty_factor**penalty_count)
            candidate_distance = current_distance + penalized_weight
            if candidate_distance + 1e-12 < distances[edge.target]:
                distances[edge.target] = candidate_distance
                previous[edge.target] = (current_node, edge)
                step_counter += 1
                heapq.heappush(queue, (candidate_distance, step_counter, edge.target))

    if math.isinf(distances[destination_id]):
        raise ValueError(
            f"No path was found from '{origin_id}' to '{destination_id}'. "
            "Check graph connectivity or active node filters."
        )

    ordered_nodes = [destination_id]
    traversed_edges: list[GraphEdge] = []
    cursor = destination_id
    while cursor != origin_id:
        previous_record = previous[cursor]
        if previous_record is None:
            raise ValueError("Path reconstruction failed even though a route was found.")
        previous_node, incoming_edge = previous_record
        ordered_nodes.append(previous_node)
        traversed_edges.append(incoming_edge)
        cursor = previous_node

    ordered_nodes.reverse()
    traversed_edges.reverse()

    return assemble_route_result(
        nodes=nodes,
        ordered_nodes=ordered_nodes,
        traversed_edges=traversed_edges,
        route_id=route_id,
        optimized_weight=distances[destination_id],
    )
