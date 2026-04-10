from __future__ import annotations

import math
import statistics
from collections import deque
from typing import Any

from ..models import GraphEdge
from ..schemas import CriterionSchema, CustomMetricWeights, DatasetSchema
from .dijkstra_service import assemble_route_result, run_dijkstra
from .graph_service import build_graph

EPSILON = 1e-9


def _safe_label(field: str) -> str:
    return field.replace("_", " ").title()


def _prepare_edge_alternatives(
    dataset: DatasetSchema,
    active_node_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    active_set = set(active_node_ids or [node.id for node in dataset.nodes if node.active])
    alternatives: list[dict[str, Any]] = []

    for edge in dataset.edges:
        if edge.source not in active_set or edge.target not in active_set:
            continue

        metadata = dict(edge.metadata)
        alternative = {
            "alternative_id": metadata.get("__edge_id", f"{edge.source}->{edge.target}"),
            "alternative_label": metadata.get("__edge_label", f"{edge.source} -> {edge.target}"),
            "source": edge.source,
            "target": edge.target,
            "distance": float(edge.distance),
            "time": float(edge.time),
            "cost": float(edge.cost),
            "road_condition_score": float(edge.road_condition_score),
            "metadata": metadata,
        }
        for key, value in metadata.items():
            if key.startswith("__") or key.startswith("_"):
                continue
            if isinstance(value, bool):
                continue
            if isinstance(value, (int, float)):
                alternative[key] = float(value)
        alternatives.append(alternative)

    return alternatives


def get_available_edge_criteria(
    dataset: DatasetSchema,
    active_node_ids: list[str] | None = None,
) -> list[dict[str, str]]:
    alternatives = _prepare_edge_alternatives(dataset, active_node_ids)
    if not alternatives:
      return []

    label_map = alternatives[0].get("metadata", {}).get("__column_labels__", {})
    fields: list[dict[str, str]] = []

    for candidate_field in ("distance", "time", "cost", "road_condition_score"):
        if any(candidate_field in alternative for alternative in alternatives):
            label = label_map.get(candidate_field, _safe_label(candidate_field))
            fields.append({"field": candidate_field, "label": label})

    numeric_metadata_fields = sorted(
        {
            key
            for alternative in alternatives
            for key, value in alternative.items()
            if key not in {"alternative_id", "alternative_label", "source", "target", "metadata", "distance", "time", "cost", "road_condition_score"}
            and isinstance(value, (int, float))
        }
    )
    for field_name in numeric_metadata_fields:
        label = label_map.get(field_name, _safe_label(field_name))
        fields.append({"field": field_name, "label": label})

    return fields


def _get_value(alternative: dict[str, Any], field: str, criterion: dict[str, Any]) -> float:
    if field.startswith("manual::"):
        manual_values = criterion.get("manual_values", {})
        if alternative["alternative_id"] not in manual_values:
            raise ValueError(
                f"Manual criterion '{criterion['label']}' is missing a value for alternative '{alternative['alternative_label']}'."
            )
        return float(manual_values[alternative["alternative_id"]])

    if field not in alternative:
        raise ValueError(f"Criterion field '{field}' is not available in the imported edge data.")
    return float(alternative[field])


def _normalized_column(values: list[float], kind: str) -> list[float]:
    max_value = max(values) if values else 0.0
    min_value = min(values) if values else 0.0
    normalized: list[float] = []

    for value in values:
        if kind == "benefit":
            normalized.append(value / max_value if max_value else 0.0)
        else:
            if value == 0:
                normalized.append(1.0 if min_value == 0 else 0.0)
            else:
                normalized.append(min_value / value)
    return normalized


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _std_population(values: list[float]) -> float:
    if not values:
        return 0.0
    mean_value = _mean(values)
    return math.sqrt(sum((value - mean_value) ** 2 for value in values) / len(values))


def _pearson(x_values: list[float], y_values: list[float]) -> float:
    if len(x_values) != len(y_values) or len(x_values) < 2:
        return 0.0
    mean_x = _mean(x_values)
    mean_y = _mean(y_values)
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(x_values, y_values))
    denominator_x = math.sqrt(sum((x - mean_x) ** 2 for x in x_values))
    denominator_y = math.sqrt(sum((y - mean_y) ** 2 for y in y_values))
    denominator = denominator_x * denominator_y
    return numerator / denominator if denominator else 0.0


def resolve_weight_strategy(
    alternatives: list[dict[str, Any]],
    criteria_payload: list[dict[str, Any]],
    weight_method: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not criteria_payload:
        raise ValueError("Please select at least one criterion for the hybrid analysis.")

    resolved_criteria = [dict(item) for item in criteria_payload]

    if weight_method == "manual":
        total_weight = sum(float(item.get("weight", 0.0)) for item in resolved_criteria)
        if total_weight <= 0:
            raise ValueError("Manual weights must have a positive total.")
        normalized_weights = [float(item.get("weight", 0.0)) / total_weight for item in resolved_criteria]
    elif weight_method == "equal":
        normalized_weights = [1.0 / len(resolved_criteria)] * len(resolved_criteria)
    else:
        oriented_columns: dict[str, list[float]] = {}
        for criterion in resolved_criteria:
            column_values = [_get_value(alternative, criterion["field"], criterion) for alternative in alternatives]
            oriented_columns[criterion["field"]] = _normalized_column(column_values, criterion["kind"])

        if weight_method == "stddev":
            raw_weights = [_std_population(oriented_columns[criterion["field"]]) for criterion in resolved_criteria]
        elif weight_method == "critic":
            raw_weights = []
            for criterion in resolved_criteria:
                field = criterion["field"]
                sigma = _std_population(oriented_columns[field])
                conflict = 0.0
                for other_criterion in resolved_criteria:
                    other_field = other_criterion["field"]
                    if field == other_field:
                        continue
                    conflict += 1 - _pearson(oriented_columns[field], oriented_columns[other_field])
                raw_weights.append(sigma * conflict)
        else:
            raise ValueError(f"Unsupported weight method: {weight_method}.")

        total_weight = sum(raw_weights)
        if total_weight <= 0:
            normalized_weights = [1.0 / len(resolved_criteria)] * len(resolved_criteria)
        else:
            normalized_weights = [weight / total_weight for weight in raw_weights]

        for criterion, raw_weight in zip(resolved_criteria, raw_weights):
            criterion["raw_weight"] = round(raw_weight, 6)

    weights_table: list[dict[str, Any]] = []
    for criterion, normalized_weight in zip(resolved_criteria, normalized_weights):
        raw_weight = float(criterion.get("weight", criterion.get("raw_weight", normalized_weight)))
        criterion["weight"] = normalized_weight
        weights_table.append(
            {
                "criterion": criterion["label"],
                "field": criterion["field"],
                "kind": criterion["kind"],
                "raw_weight": round(raw_weight, 6),
                "normalized_weight": round(normalized_weight, 6),
            }
        )

    weights_table.append(
        {
            "criterion": "Sigma",
            "field": "-",
            "kind": "-",
            "raw_weight": round(sum(item["raw_weight"] for item in weights_table if isinstance(item["raw_weight"], (int, float))), 6),
            "normalized_weight": round(sum(item["normalized_weight"] for item in weights_table), 6),
        }
    )
    return resolved_criteria, weights_table


def evaluate_edge_alternatives(
    alternatives: list[dict[str, Any]],
    criteria: list[dict[str, Any]],
    method: str,
) -> dict[str, Any]:
    if not alternatives:
        raise ValueError("No alternatives are available for MCDM evaluation.")
    if not criteria:
        raise ValueError("No criteria are available for MCDM evaluation.")

    decision_matrix: list[dict[str, Any]] = []
    raw_by_field: dict[str, list[float]] = {criterion["field"]: [] for criterion in criteria}

    for alternative in alternatives:
        row = {"alternative_id": alternative["alternative_id"], "alternative_label": alternative["alternative_label"]}
        for criterion in criteria:
            value = _get_value(alternative, criterion["field"], criterion)
            row[criterion["label"]] = round(value, 6)
            raw_by_field[criterion["field"]].append(value)
        decision_matrix.append(row)

    if method == "saw":
        return _evaluate_saw_generic(alternatives, criteria, raw_by_field, decision_matrix)
    if method == "topsis":
        return _evaluate_topsis_generic(alternatives, criteria, raw_by_field, decision_matrix)
    raise ValueError(f"Unsupported MCDM method: {method}.")


def _evaluate_saw_generic(
    alternatives: list[dict[str, Any]],
    criteria: list[dict[str, Any]],
    raw_by_field: dict[str, list[float]],
    decision_matrix: list[dict[str, Any]],
) -> dict[str, Any]:
    normalized_matrix: list[dict[str, Any]] = []
    weighted_matrix: list[dict[str, Any]] = []
    ranking: list[dict[str, Any]] = []

    for alternative in alternatives:
        normalized_row = {
            "alternative_id": alternative["alternative_id"],
            "alternative_label": alternative["alternative_label"],
        }
        weighted_row = {
            "alternative_id": alternative["alternative_id"],
            "alternative_label": alternative["alternative_label"],
        }
        total_score = 0.0

        for criterion in criteria:
            value = _get_value(alternative, criterion["field"], criterion)
            column_values = raw_by_field[criterion["field"]]
            max_value = max(column_values) if column_values else 0.0
            min_value = min(column_values) if column_values else 0.0

            if criterion["kind"] == "benefit":
                normalized_value = value / max_value if max_value else 0.0
            else:
                if value == 0:
                    normalized_value = 1.0 if min_value == 0 else 0.0
                else:
                    normalized_value = min_value / value

            weighted_value = normalized_value * criterion["weight"]
            normalized_row[criterion["label"]] = round(normalized_value, 6)
            weighted_row[criterion["label"]] = round(weighted_value, 6)
            total_score += weighted_value

        normalized_matrix.append(normalized_row)
        weighted_matrix.append(weighted_row)
        ranking.append(
            {
                "alternative_id": alternative["alternative_id"],
                "alternative_label": alternative["alternative_label"],
                "score": round(total_score, 6),
            }
        )

    ranking.sort(key=lambda item: (-item["score"], item["alternative_label"]))
    for index, row in enumerate(ranking, start=1):
        row["rank"] = index

    return {
        "decision_matrix": decision_matrix,
        "normalized_matrix": normalized_matrix,
        "weighted_matrix": weighted_matrix,
        "ranking": ranking,
    }


def _evaluate_topsis_generic(
    alternatives: list[dict[str, Any]],
    criteria: list[dict[str, Any]],
    raw_by_field: dict[str, list[float]],
    decision_matrix: list[dict[str, Any]],
) -> dict[str, Any]:
    normalized_matrix: list[dict[str, Any]] = []
    weighted_matrix: list[dict[str, Any]] = []
    weighted_lookup: dict[str, dict[str, float]] = {}

    for alternative in alternatives:
        normalized_row = {
            "alternative_id": alternative["alternative_id"],
            "alternative_label": alternative["alternative_label"],
        }
        weighted_row = {
            "alternative_id": alternative["alternative_id"],
            "alternative_label": alternative["alternative_label"],
        }
        weighted_values: dict[str, float] = {}

        for criterion in criteria:
            value = _get_value(alternative, criterion["field"], criterion)
            column_values = raw_by_field[criterion["field"]]
            denominator = math.sqrt(sum(item ** 2 for item in column_values))
            normalized_value = value / denominator if denominator else 0.0
            weighted_value = normalized_value * criterion["weight"]
            normalized_row[criterion["label"]] = round(normalized_value, 6)
            weighted_row[criterion["label"]] = round(weighted_value, 6)
            weighted_values[criterion["label"]] = weighted_value

        normalized_matrix.append(normalized_row)
        weighted_matrix.append(weighted_row)
        weighted_lookup[alternative["alternative_id"]] = weighted_values

    ideal_positive: dict[str, float] = {}
    ideal_negative: dict[str, float] = {}
    for criterion in criteria:
        label = criterion["label"]
        column = [row[label] for row in weighted_matrix]
        if criterion["kind"] == "benefit":
            ideal_positive[label] = max(column)
            ideal_negative[label] = min(column)
        else:
            ideal_positive[label] = min(column)
            ideal_negative[label] = max(column)

    ranking: list[dict[str, Any]] = []
    for alternative in alternatives:
        weighted_values = weighted_lookup[alternative["alternative_id"]]
        distance_positive = math.sqrt(
            sum((weighted_values[label] - ideal_positive[label]) ** 2 for label in weighted_values)
        )
        distance_negative = math.sqrt(
            sum((weighted_values[label] - ideal_negative[label]) ** 2 for label in weighted_values)
        )
        denominator = distance_positive + distance_negative
        closeness = distance_negative / denominator if denominator else 0.0
        ranking.append(
            {
                "alternative_id": alternative["alternative_id"],
                "alternative_label": alternative["alternative_label"],
                "score": round(closeness, 6),
            }
        )

    ranking.sort(key=lambda item: (-item["score"], item["alternative_label"]))
    for index, row in enumerate(ranking, start=1):
        row["rank"] = index

    return {
        "decision_matrix": decision_matrix,
        "normalized_matrix": normalized_matrix,
        "weighted_matrix": weighted_matrix,
        "ranking": ranking,
    }


def _build_edge_score_overrides(edge_alternatives: list[dict[str, Any]], ranking: list[dict[str, Any]]) -> dict[tuple[str, str], float]:
    ranking_lookup = {row["alternative_id"]: row["score"] for row in ranking}
    weight_overrides: dict[tuple[str, str], float] = {}
    for alternative in edge_alternatives:
        score = ranking_lookup.get(alternative["alternative_id"], EPSILON)
        weight_overrides[(alternative["source"], alternative["target"])] = 1.0 / max(score, EPSILON)
    return weight_overrides


def _compute_reachable_nodes(graph_bundle: dict[str, Any], destination_id: str) -> set[str]:
    adjacency = graph_bundle["adjacency"]
    reverse_lookup: dict[str, set[str]] = {node_id: set() for node_id in adjacency}
    for source, edges in adjacency.items():
        for edge in edges:
            reverse_lookup.setdefault(edge.target, set()).add(source)

    visited = {destination_id}
    queue = deque([destination_id])
    while queue:
        node_id = queue.popleft()
        for predecessor in reverse_lookup.get(node_id, set()):
            if predecessor not in visited:
                visited.add(predecessor)
                queue.append(predecessor)
    return visited


def _identify_edge_alternative(edge: GraphEdge, edge_alternatives: list[dict[str, Any]]) -> dict[str, Any]:
    edge_id = edge.metadata.get("__edge_id")
    if edge_id:
        for alternative in edge_alternatives:
            if alternative["alternative_id"] == edge_id:
                return alternative

    for alternative in edge_alternatives:
        if (
            alternative["source"] == edge.source
            and alternative["target"] == edge.target
            and math.isclose(alternative["time"], edge.time)
        ):
            return alternative

    for alternative in edge_alternatives:
        if (
            alternative["source"] == edge.target
            and alternative["target"] == edge.source
            and math.isclose(alternative["time"], edge.time)
            and math.isclose(alternative["distance"], edge.distance)
            and math.isclose(alternative["cost"], edge.cost)
        ):
            return alternative
    raise ValueError(f"Could not map edge '{edge.source} -> {edge.target}' back to imported edge data.")


def run_hybrid_analysis(
    dataset: DatasetSchema,
    origin_id: str,
    destination_id: str,
    graph_type: str,
    criteria_payload: list[dict[str, Any]],
    mcdm_method: str,
    weight_method: str,
    scenario: str,
    active_node_ids: list[str] | None = None,
) -> dict[str, Any]:
    edge_alternatives = _prepare_edge_alternatives(dataset, active_node_ids)
    resolved_criteria, weights_table = resolve_weight_strategy(edge_alternatives, criteria_payload, weight_method)

    if scenario == "scenario_1":
        global_mcdm = evaluate_edge_alternatives(edge_alternatives, resolved_criteria, mcdm_method)
        graph_bundle = build_graph(
            dataset=dataset,
            graph_type=graph_type,
            metric="time",
            active_node_ids=active_node_ids,
            edge_weight_overrides=_build_edge_score_overrides(edge_alternatives, global_mcdm["ranking"]),
        )
        route_result = run_dijkstra(graph_bundle, origin_id, destination_id)
        explanation = (
            "Scenario 1 computes MCDM utility on all imported edges first, then transforms the utility "
            "into positive Dijkstra edge costs using inverse utility."
        )
        return {
            "scenario": scenario,
            "method": mcdm_method,
            "weight_method": weight_method,
            "criteria": resolved_criteria,
            "weights_table": weights_table,
            "edge_alternatives": [
                {
                    "alternative_id": alternative["alternative_id"],
                    "alternative_label": alternative["alternative_label"],
                    "source": alternative["source"],
                    "target": alternative["target"],
                }
                for alternative in edge_alternatives
            ],
            "decision_matrix": global_mcdm["decision_matrix"],
            "normalized_matrix": global_mcdm["normalized_matrix"],
            "weighted_matrix": global_mcdm["weighted_matrix"],
            "ranking": global_mcdm["ranking"],
            "route_result": route_result,
            "local_steps": [],
            "explanation": explanation,
        }

    if scenario != "scenario_2":
        raise ValueError(f"Unsupported hybrid scenario: {scenario}.")

    graph_bundle = build_graph(
        dataset=dataset,
        graph_type=graph_type,
        metric="time",
        active_node_ids=active_node_ids,
    )
    adjacency = graph_bundle["adjacency"]
    nodes = graph_bundle["nodes"]
    reachable_nodes = _compute_reachable_nodes(graph_bundle, destination_id)
    if origin_id not in reachable_nodes:
        raise ValueError(f"Destination '{destination_id}' is not reachable from origin '{origin_id}'.")

    current_node = origin_id
    visited_nodes = {origin_id}
    ordered_nodes = [origin_id]
    traversed_edges: list[GraphEdge] = []
    local_steps: list[dict[str, Any]] = []
    cumulative_weight = 0.0

    while current_node != destination_id:
        candidates = []
        for edge in adjacency[current_node]:
            if edge.target != destination_id and edge.target in visited_nodes:
                continue
            if edge.target not in reachable_nodes:
                continue
            candidates.append(edge)

        if not candidates:
            raise ValueError(
                "Scenario 2 stopped before reaching the destination. "
                "No locally feasible edge remained under the current greedy MCDM rule."
            )

        candidate_alternatives = [_identify_edge_alternative(edge, edge_alternatives) for edge in candidates]
        local_mcdm = evaluate_edge_alternatives(candidate_alternatives, resolved_criteria, mcdm_method)
        best_choice = local_mcdm["ranking"][0]
        selected_edge = next(
            edge for edge in candidates if _identify_edge_alternative(edge, edge_alternatives)["alternative_id"] == best_choice["alternative_id"]
        )
        local_cost = 1.0 / max(best_choice["score"], EPSILON)
        traversed_edges.append(
            GraphEdge(
                source=selected_edge.source,
                target=selected_edge.target,
                distance=selected_edge.distance,
                time=selected_edge.time,
                cost=selected_edge.cost,
                road_condition_score=selected_edge.road_condition_score,
                computed_weight=local_cost,
                metadata=selected_edge.metadata,
            )
        )
        cumulative_weight += local_cost
        current_node = selected_edge.target
        ordered_nodes.append(current_node)
        visited_nodes.add(current_node)
        local_steps.append(
            {
                "from_node": ordered_nodes[-2],
                "to_node": current_node,
                "decision_matrix": local_mcdm["decision_matrix"],
                "ranking": local_mcdm["ranking"],
                "selected_alternative_id": best_choice["alternative_id"],
                "selected_alternative_label": best_choice["alternative_label"],
                "selected_score": best_choice["score"],
            }
        )

        if len(ordered_nodes) > len(nodes) + len(adjacency):
            raise ValueError("Scenario 2 exceeded a safe step limit and may be cycling.")

    route_result = assemble_route_result(
        nodes=nodes,
        ordered_nodes=ordered_nodes,
        traversed_edges=traversed_edges,
        route_id="R1",
        optimized_weight=cumulative_weight,
    )
    explanation = (
        "Scenario 2 applies MCDM only to the currently available outgoing edges at each step. "
        "This is a greedy local-selection process, so it does not guarantee the same global optimum as Dijkstra."
    )
    return {
        "scenario": scenario,
        "method": mcdm_method,
        "weight_method": weight_method,
        "criteria": resolved_criteria,
        "weights_table": weights_table,
        "edge_alternatives": [
            {
                "alternative_id": alternative["alternative_id"],
                "alternative_label": alternative["alternative_label"],
                "source": alternative["source"],
                "target": alternative["target"],
            }
            for alternative in edge_alternatives
        ],
        "decision_matrix": [],
        "normalized_matrix": [],
        "weighted_matrix": [],
        "ranking": [],
        "route_result": route_result,
        "local_steps": local_steps,
        "explanation": explanation,
    }
