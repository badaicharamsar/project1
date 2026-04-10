from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Node:
    """Internal node model used by graph algorithms."""

    id: str
    name: str
    latitude: float
    longitude: float
    metadata: dict[str, Any] = field(default_factory=dict)
    active: bool = True


@dataclass(slots=True)
class Edge:
    """Internal edge model as entered by the user or loaded from files."""

    source: str
    target: str
    distance: float
    time: float
    cost: float
    road_condition_score: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class GraphEdge:
    """Prepared edge with a computed optimization weight for Dijkstra."""

    source: str
    target: str
    distance: float
    time: float
    cost: float
    road_condition_score: float
    computed_weight: float
    metadata: dict[str, Any] = field(default_factory=dict)
