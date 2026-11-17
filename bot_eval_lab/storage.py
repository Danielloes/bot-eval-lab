"""SQLite: a execução inteira entra em uma única transação."""

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def connection(path: Path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    try:
        db.execute("PRAGMA foreign_keys = ON")
        db.executescript("""
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                dataset_hash TEXT NOT NULL,
                policy_hash TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS results (
                run_id TEXT NOT NULL REFERENCES runs(id),
                case_id TEXT NOT NULL,
                result_json TEXT NOT NULL,
                PRIMARY KEY (run_id, case_id)
            );
        """)
        yield db
    finally:
        db.close()


def save_run(path: Path, run: dict) -> None:
    expected_ids = {c["id"] for c in run["dataset"]["cases"]}
    result_ids = [r["case"]["id"] for r in run["results"]]
    if not expected_ids or set(result_ids) != expected_ids or len(result_ids) != len(expected_ids):
        raise ValueError("Execução incompleta: resultados ausentes ou duplicados; nada foi salvo")
    metadata = {key: value for key, value in run.items() if key != "results"}
    with connection(path) as db, db:
        db.execute("INSERT INTO runs VALUES (?, ?, ?, ?, ?)",
                   (run["id"], run["created_at"], run["dataset_hash"], run["policy_hash"],
                    json.dumps(metadata, ensure_ascii=False)))
        # Se serialização/inserção falhar, o context manager desfaz inclusive runs.
        for result in run["results"]:
            db.execute("INSERT INTO results VALUES (?, ?, ?)",
                       (run["id"], result["case"]["id"], json.dumps(result, ensure_ascii=False)))


def load_run(path: Path, run_id: str) -> dict:
    with connection(path) as db:
        row = db.execute("SELECT metadata_json FROM runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            raise ValueError(f"Execução não encontrada: {run_id}")
        run = json.loads(row[0])
        run["results"] = [json.loads(r[0]) for r in db.execute(
            "SELECT result_json FROM results WHERE run_id = ? ORDER BY case_id", (run_id,))]
    if len(run["results"]) != len(run["dataset"]["cases"]):
        raise ValueError("Execução incompleta no banco; comparação bloqueada")
    return run


def list_runs(path: Path) -> list[dict]:
    with connection(path) as db:
        return [json.loads(row[0]) for row in db.execute("SELECT metadata_json FROM runs ORDER BY created_at")]
