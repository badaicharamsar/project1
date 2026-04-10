from __future__ import annotations

from collections import defaultdict
from typing import Any

from .dijkstra_service import run_dijkstra


def generate_alternative_routes(
    graph_bundle: dict[str, Any],
    origin_id: str,
    destination_id: str,
    max_routes: int = 3,
    penalty_factor: float = 1.35,
) -> list[dict[str, Any]]:
    """Generate simple deterministic alternatives by penalizing previously chosen edges."""

    if max_routes < 1:
        raise ValueError("max_routes must be at least 1.")

    alternatives: list[dict[str, Any]] = []
    seen_paths: set[tuple[str, ...]] = set()
    penalty_lookup: dict[tuple[str, str], int] = defaultdict(int)
    max_attempts = max_routes * 5

    for _ in range(max_attempts):
        route = run_dijkstra(
            graph_bundle=graph_bundle,
            origin_id=origin_id,
            destination_id=destination_id,
            penalty_lookup=penalty_lookup,
            penalty_factor=penalty_factor,
            route_id=f"R{len(alternatives) + 1}",
        )
        route["optimized_weight"] = round(
            sum(edge["optimized_weight"] for edge in route["traversed_edges"]),
            6,
        )
        path_signature = tuple(route["path_nodes"])

        for edge in route["traversed_edges"]:
            penalty_lookup[(edge["source"], edge["target"])] += 1
            if graph_bundle["graph_type"] == "undirected":
                penalty_lookup[(edge["target"], edge["source"])] += 1

        if path_signature in seen_paths:
            continue

        seen_paths.add(path_signature)
        alternatives.append(route)
        if len(alternatives) >= max_routes:
            break

    if not alternatives:
        raise ValueError("No alternative routes could be generated for the given graph.")

    return alternatives
