from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from .models import PredictionReport, Project, SimulationRun


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = PROJECT_ROOT / "data" / "prediction_engine"


class PredictionStorage:
    def __init__(self, data_dir: str | Path | None = None) -> None:
        self.data_dir = Path(data_dir) if data_dir else DEFAULT_DATA_DIR
        self.uploads_dir = self.data_dir / "uploads"
        self.reports_dir = self.data_dir / "reports"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "prediction_engine.sqlite3"
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with closing(self._connect()) as conn, conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    question TEXT NOT NULL,
                    material_name TEXT NOT NULL,
                    material_path TEXT NOT NULL,
                    material_text TEXT NOT NULL,
                    summary_json TEXT NOT NULL,
                    ontology_json TEXT NOT NULL DEFAULT '{}',
                    graph_json TEXT NOT NULL DEFAULT '{}',
                    environment_json TEXT NOT NULL DEFAULT '{}',
                    entities_json TEXT NOT NULL,
                    factors_json TEXT NOT NULL,
                    agents_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    params_json TEXT NOT NULL,
                    events_json TEXT NOT NULL,
                    metrics_json TEXT NOT NULL,
                    report_id TEXT,
                    created_at TEXT NOT NULL,
                    completed_at TEXT,
                    FOREIGN KEY(project_id) REFERENCES projects(id)
                );

                CREATE TABLE IF NOT EXISTS reports (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    report_json TEXT NOT NULL,
                    markdown TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(project_id) REFERENCES projects(id),
                    FOREIGN KEY(run_id) REFERENCES runs(id)
                );

                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    run_id TEXT,
                    status TEXT NOT NULL,
                    progress INTEGER NOT NULL,
                    message TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS simulations (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    graph_id TEXT,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(project_id) REFERENCES projects(id)
                );
                """
            )
            self._ensure_project_columns(conn)

    def _ensure_project_columns(self, conn: sqlite3.Connection) -> None:
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(projects)").fetchall()}
        additions = {
            "ontology_json": "TEXT NOT NULL DEFAULT '{}'",
            "graph_json": "TEXT NOT NULL DEFAULT '{}'",
            "environment_json": "TEXT NOT NULL DEFAULT '{}'",
        }
        for name, definition in additions.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE projects ADD COLUMN {name} {definition}")

    def save_project(self, project: Project) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO projects (
                    id, title, question, material_name, material_path, material_text,
                    summary_json, ontology_json, graph_json, environment_json,
                    entities_json, factors_json, agents_json,
                    status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project.id,
                    project.title,
                    project.question,
                    project.material_name,
                    project.material_path,
                    project.material_text,
                    _json(project.summary),
                    _json(project.ontology),
                    _json(project.graph),
                    _json(project.environment),
                    _json(project.entities),
                    _json(project.factors),
                    _json(project.agents),
                    project.status,
                    project.created_at,
                    project.updated_at,
                ),
            )

    def get_project(self, project_id: str) -> Project | None:
        with closing(self._connect()) as conn, conn:
            row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        return _project_from_row(row) if row else None

    def list_projects(self, limit: int = 8) -> list[dict[str, Any]]:
        with closing(self._connect()) as conn, conn:
            rows = conn.execute(
                "SELECT * FROM projects ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [_project_from_row(row).to_dict() for row in rows]

    def save_run(self, run: SimulationRun) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO runs (
                    id, project_id, status, params_json, events_json, metrics_json,
                    report_id, created_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run.id,
                    run.project_id,
                    run.status,
                    _json(run.params),
                    _json(run.events),
                    _json(run.metrics),
                    run.report_id,
                    run.created_at,
                    run.completed_at,
                ),
            )

    def get_run(self, run_id: str) -> SimulationRun | None:
        with closing(self._connect()) as conn, conn:
            row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        return _run_from_row(row) if row else None

    def save_report(self, report: PredictionReport) -> None:
        import re
        if not isinstance(report.id,str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}",report.id):raise ValueError("报告ID须为安全的单一路径组件")
        report_path = self.reports_dir / f"{report.id}.md"
        report_path.write_text(report.markdown, "utf-8")
        with closing(self._connect()) as conn, conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO reports (
                    id, project_id, run_id, report_json, markdown, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    report.id,
                    report.project_id,
                    report.run_id,
                    _json(report.to_dict()),
                    report.markdown,
                    report.created_at,
                ),
            )

    def get_report(self, report_id: str) -> PredictionReport | None:
        with closing(self._connect()) as conn, conn:
            row = conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
        if not row:
            return None
        data = json.loads(row["report_json"])
        return PredictionReport(**data)

    def save_job(self, job: dict[str, Any]) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO jobs (
                    id, run_id, status, progress, message, result_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job["id"],
                    job.get("run_id"),
                    job["status"],
                    int(job["progress"]),
                    job["message"],
                    _json(job.get("result", {})),
                    job["created_at"],
                    job["updated_at"],
                ),
            )

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with closing(self._connect()) as conn, conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "run_id": row["run_id"],
            "status": row["status"],
            "progress": row["progress"],
            "message": row["message"],
            "result": json.loads(row["result_json"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def save_simulation(self, simulation: dict[str, Any]) -> None:
        payload = dict(simulation)
        simulation_id = str(payload.get("simulation_id") or payload.get("id") or "")
        if not simulation_id:
            raise ValueError("simulation_id 不能为空")
        payload["simulation_id"] = simulation_id
        payload["id"] = simulation_id
        with closing(self._connect()) as conn, conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO simulations (
                    id, project_id, graph_id, status, payload_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    simulation_id,
                    payload["project_id"],
                    payload.get("graph_id"),
                    payload.get("status", "created"),
                    _json(payload),
                    payload.get("created_at"),
                    payload.get("updated_at"),
                ),
            )

    def get_simulation(self, simulation_id: str) -> dict[str, Any] | None:
        with closing(self._connect()) as conn, conn:
            row = conn.execute("SELECT * FROM simulations WHERE id = ?", (simulation_id,)).fetchone()
        if not row:
            return None
        return json.loads(row["payload_json"])

    def list_simulations(self, limit: int = 20, project_id: str | None = None) -> list[dict[str, Any]]:
        with closing(self._connect()) as conn, conn:
            if project_id:
                rows = conn.execute(
                    "SELECT * FROM simulations WHERE project_id = ? ORDER BY created_at DESC LIMIT ?",
                    (project_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM simulations ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def find_project_by_graph_id(self, graph_id: str) -> Project | None:
        for project in self.list_projects(limit=-1):
            graph = project.get("graph") or {}
            if graph.get("graph_id") == graph_id:
                return self.get_project(project["id"])
        return None


def _json(value: Any) -> str:
    if is_dataclass(value):
        value = asdict(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _project_from_row(row: sqlite3.Row) -> Project:
    return Project(
        id=row["id"],
        title=row["title"],
        question=row["question"],
        material_name=row["material_name"],
        material_path=row["material_path"],
        material_text=row["material_text"],
        summary=json.loads(row["summary_json"]),
        ontology=json.loads(row["ontology_json"] or "{}"),
        graph=json.loads(row["graph_json"] or "{}"),
        environment=json.loads(row["environment_json"] or "{}"),
        entities=json.loads(row["entities_json"]),
        factors=json.loads(row["factors_json"]),
        agents=json.loads(row["agents_json"]),
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _run_from_row(row: sqlite3.Row) -> SimulationRun:
    return SimulationRun(
        id=row["id"],
        project_id=row["project_id"],
        status=row["status"],
        params=json.loads(row["params_json"]),
        events=json.loads(row["events_json"]),
        metrics=json.loads(row["metrics_json"]),
        report_id=row["report_id"],
        created_at=row["created_at"],
        completed_at=row["completed_at"],
    )
