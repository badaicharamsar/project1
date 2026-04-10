from __future__ import annotations

import math
from typing import Any

from ..schemas import CriterionSchema

SUPPORTED_FIELDS = {
    "total_distance",
    "total_time",
    "total_cost",
    "average_road_condition",
    "hops",
    "optimized_weight",
}


def _round_row(route_id: str, values: dict[str, float]) -> dict[str, Any]:
    return {"route_id": route_id, **{key: round(value, 6) for key, value in values.items()}}


def _extract_value(alternative: dict[str, Any], field: str) -> float:
    if field in SUPPORTED_FIELDS:
        return float(alternative[field])

    extra_metrics = alternative.get("extra_metrics", {})
    if field in extra_metrics:
        return float(extra_metrics[field])

    supported = sorted(SUPPORTED_FIELDS | set(extra_metrics.keys()))
    raise ValueError(
        f"Unsupported criterion field '{field}'. "
        f"Available fields for the current alternatives are: {supported}."
    )


def _normalize_weights(criteria: list[CriterionSchema]) -> list[CriterionSchema]:
    total_weight = sum(item.weight for item in criteria)
    if total_weight <= 0:
        raise ValueError("At least one criterion weight must be positive.")
    return [
        CriterionSchema(
            field=item.field,
            label=item.label,
            kind=item.kind,
            weight=item.weight / total_weight,
        )
        for item in criteria
    ]


def evaluate_routes(
    alternatives: list[dict[str, Any]],
    criteria: list[CriterionSchema],
    method: str,
) -> dict[str, Any]:
    if not alternatives:
        raise ValueError("MCDM evaluation requires at least one route alternative.")
    if not criteria:
        raise ValueError("Please define at least one evaluation criterion.")

    normalized_criteria = _normalize_weights(criteria)
    decision_matrix: list[dict[str, Any]] = []
    raw_by_criterion: dict[str, list[float]] = {criterion.field: [] for criterion in normalized_criteria}

    for alternative in alternatives:
        row_values: dict[str, float] = {}
        for criterion in normalized_criteria:
            value = _extract_value(alternative, criterion.field)
            row_values[criterion.label] = value
            raw_by_criterion[criterion.field].append(value)
        decision_matrix.append(_round_row(alternative["route_id"], row_values))

    if method == "saw":
        return _evaluate_saw(alternatives, normalized_criteria, raw_by_criterion, decision_matrix)
    if method == "topsis":
        return _evaluate_topsis(alternatives, normalized_criteria, raw_by_criterion, decision_matrix)
    raise ValueError(f"Unsupported MCDM method: {method}.")


def _evaluate_saw(
    alternatives: list[dict[str, Any]],
    criteria: list[CriterionSchema],
    raw_by_criterion: dict[str, list[float]],
    decision_matrix: list[dict[str, Any]],
) -> dict[str, Any]:
    normalized_matrix: list[dict[str, Any]] = []
    weighted_matrix: list[dict[str, Any]] = []
    scores: list[dict[str, Any]] = []

    for alternative in alternatives:
        normalized_values: dict[str, float] = {}
        weighted_values: dict[str, float] = {}

        for criterion in criteria:
            current_value = _extract_value(alternative, criterion.field)
            column_values = raw_by_criterion[criterion.field]
            column_max = max(column_values) if column_values else 0.0
            column_min = min(column_values) if column_values else 0.0

            # SAW normalization:
            # Benefit criterion  : r_ij = x_ij / max(x_j)
            # Cost criterion     : r_ij = min(x_j) / x_ij
            if criterion.kind == "benefit":
                normalized_value = current_value / column_max if column_max else 0.0
            else:
                if current_value == 0:
                    normalized_value = 1.0 if column_min == 0 else 0.0
                else:
                    normalized_value = column_min / current_value

            normalized_values[criterion.label] = normalized_value
            weighted_values[criterion.label] = normalized_value * criterion.weight

        normalized_matrix.append(_round_row(alternative["route_id"], normalized_values))
        weighted_matrix.append(_round_row(alternative["route_id"], weighted_values))
        scores.append(
            {
                "route_id": alternative["route_id"],
                "score": round(sum(weighted_values.values()), 6),
            }
        )

    ranking = _rank_scores(scores)
    return {
        "method": "saw",
        "criteria": [criterion.model_dump() for criterion in criteria],
        "decision_matrix": decision_matrix,
        "normalized_matrix": normalized_matrix,
        "weighted_matrix": weighted_matrix,
        "ranking": ranking,
        "explanation": _build_explanation(ranking, "SAW"),
    }


def _evaluate_topsis(
    alternatives: list[dict[str, Any]],
    criteria: list[CriterionSchema],
    raw_by_criterion: dict[str, list[float]],
    decision_matrix: list[dict[str, Any]],
) -> dict[str, Any]:
    normalized_matrix: list[dict[str, Any]] = []
    weighted_matrix: list[dict[str, Any]] = []
    weighted_rows_by_route: dict[str, dict[str, float]] = {}

    for alternative in alternatives:
        normalized_values: dict[str, float] = {}
        weighted_values: dict[str, float] = {}

        for criterion in criteria:
            current_value = _extract_value(alternative, criterion.field)
            column_values = raw_by_criterion[criterion.field]

            # TOPSIS vector normalization:
            # r_ij = x_ij / sqrt(sum_i x_ij^2)
            denominator = math.sqrt(sum(value**2 for value in column_values))
            normalized_value = current_value / denominator if denominator else 0.0

            # Weighted normalized matrix:
            # v_ij = w_j * r_ij
            weighted_value = criterion.weight * normalized_value
            normalized_values[criterion.label] = normalized_value
            weighted_values[criterion.label] = weighted_value

        normalized_matrix.append(_round_row(alternative["route_id"], normalized_values))
        weighted_matrix.append(_round_row(alternative["route_id"], weighted_values))
        weighted_rows_by_route[alternative["route_id"]] = weighted_values

    ideal_positive: dict[str, float] = {}
    ideal_negative: dict[str, float] = {}
    for criterion in criteria:
        column = [row[criterion.label] for row in weighted_matrix]
        if criterion.kind == "benefit":
            ideal_positive[criterion.label] = max(column)
            ideal_negative[criterion.label] = min(column)
        else:
            ideal_positive[criterion.label] = min(column)
            ideal_negative[criterion.label] = max(column)

    scores: list[dict[str, Any]] = []
    for alternative in alternatives:
        route_id = alternative["route_id"]
        weighted_values = weighted_rows_by_route[route_id]

        # Separation from ideal positive and negative solutions:
        # D_i+ = sqrt(sum_j (v_ij - v_j+)^2)
        # D_i- = sqrt(sum_j (v_ij - v_j-)^2)
        distance_positive = math.sqrt(
            sum((weighted_values[label] - ideal_positive[label]) ** 2 for label in weighted_values)
        )
        distance_negative = math.sqrt(
            sum((weighted_values[label] - ideal_negative[label]) ** 2 for label in weighted_values)
        )

        # Closeness coefficient:
        # C_i = D_i- / (D_i+ + D_i-)
        denominator = distance_positive + distance_negative
        closeness = distance_negative / denominator if denominator else 0.0

        scores.append({"route_id": route_id, "score": round(closeness, 6)})

    ranking = _rank_scores(scores)
    return {
        "method": "topsis",
        "criteria": [criterion.model_dump() for criterion in criteria],
        "decision_matrix": decision_matrix,
        "normalized_matrix": normalized_matrix,
        "weighted_matrix": weighted_matrix,
        "ranking": ranking,
        "explanation": _build_explanation(ranking, "TOPSIS"),
    }


def _rank_scores(scores: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sorted_scores = sorted(scores, key=lambda item: (-item["score"], item["route_id"]))
    ranking: list[dict[str, Any]] = []
    for index, item in enumerate(sorted_scores, start=1):
        ranking.append({"route_id": item["route_id"], "score": item["score"], "rank": index})
    return ranking


def _build_explanation(ranking: list[dict[str, Any]], method_name: str) -> str:
    best = ranking[0]
    return (
        f"{method_name} selected {best['route_id']} as the preferred route because it obtained the "
        f"highest final preference score ({best['score']:.6f}) after combining all weighted criteria."
    )
