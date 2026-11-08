from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class Project:
    id: str
    title: str
    question: str
    material_name: str
    material_path: str
    material_text: str
    summary: dict[str, Any]
    ontology: dict[str, Any]
    graph: dict[str, Any]
    environment: dict[str, Any]
    entities: list[dict[str, Any]]
    factors: list[dict[str, Any]]
    agents: list[dict[str, Any]]
    status: str
    created_at: str
    updated_at: str

    def to_dict(self, include_text: bool = False) -> dict[str, Any]:
        data = asdict(self)
        if not include_text:
            data.pop("material_text", None)
        return data


@dataclass(frozen=True)
class AgentProfile:
    id: str
    name: str
    role: str
    stance: str
    memory: str
    bias: float
    focus: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SimulationEvent:
    round: int
    agent_id: str
    agent_name: str
    focus: str
    signal: str
    stance: str
    delta: float
    note: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SimulationRun:
    id: str
    project_id: str
    status: str
    params: dict[str, Any]
    events: list[dict[str, Any]]
    metrics: dict[str, Any]
    report_id: str | None
    created_at: str
    completed_at: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PredictionReport:
    id: str
    project_id: str
    run_id: str
    headline: str
    probability: float
    risk_level: str
    scenarios: list[dict[str, Any]]
    key_drivers: list[dict[str, Any]]
    counter_arguments: list[str]
    watch_indicators: list[str]
    next_steps: list[str]
    markdown: str
    created_at: str
    llm_note: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
