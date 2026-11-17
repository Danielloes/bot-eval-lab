import copy
import json
import sqlite3
from collections import Counter

import pytest

from bot_eval_lab.dataset import DATA, fingerprint, load_inputs
from bot_eval_lab.evaluation import compare_runs
from bot_eval_lab.storage import list_runs, load_run, save_run


def test_dataset_contract_balance_and_group_separation():
    dataset, _, _ = load_inputs(split="all")
    assert len(dataset["cases"]) >= 36
    assert min(Counter(c["expected_action"] for c in dataset["cases"]).values()) >= 8
    groups = {}
    for case in dataset["cases"]:
        groups.setdefault(case["group"], set()).add(case["split"])
    assert all(len(splits) == 1 for splits in groups.values())
    assert any(len(c["history"]) > 1 for c in dataset["cases"])


def test_rejects_group_leakage_before_selecting_split(tmp_path):
    data = json.loads((DATA / "cases.json").read_text(encoding="utf-8"))
    data["cases"][0]["split"] = "holdout"
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="Vazamento"):
        load_inputs(path, split="dev")


def test_persistence_roundtrip_and_comparison(tmp_path, runs):
    db = tmp_path / "runs.sqlite"
    for run in runs:
        save_run(db, run)
        assert load_run(db, run["id"]) == json.loads(json.dumps(run))
    comparison = compare_runs(*(load_run(db, r["id"]) for r in runs))
    assert comparison["critical_regressions"] >= 1
    assert len(list_runs(db)) == 2


@pytest.mark.parametrize("field,value", [
    ("expected_action", "clarify"), ("critical", True),
    ("expected_evidence", []), ("forbidden", ["refund_promise"]),
])
def test_rejects_changed_labels(tmp_path, runs, field, value):
    reference, candidate = runs
    candidate["dataset"]["cases"][0][field] = value
    candidate["dataset_hash"] = fingerprint(candidate["dataset"])
    for run in (reference, candidate):
        save_run(tmp_path / "runs.sqlite", run)
    with pytest.raises(ValueError, match="Conjuntos incompatíveis"):
        compare_runs(*(load_run(tmp_path / "runs.sqlite", r["id"]) for r in (reference, candidate)))


def test_rejects_different_case_set_and_evaluator(runs):
    reference, candidate = runs
    candidate["dataset"]["cases"].pop()
    candidate["dataset_hash"] = fingerprint(candidate["dataset"])
    with pytest.raises(ValueError, match="Conjuntos incompatíveis"):
        compare_runs(reference, candidate)
    candidate["dataset_hash"] = reference["dataset_hash"]
    candidate["evaluator_version"] = "different"
    with pytest.raises(ValueError, match="Avaliadores incompatíveis"):
        compare_runs(reference, candidate)


def test_partial_run_is_never_saved(tmp_path, runs):
    run = runs[0]
    run["results"].pop()
    with pytest.raises(ValueError, match="Execução incompleta"):
        save_run(tmp_path / "runs.sqlite", run)
    assert list_runs(tmp_path / "runs.sqlite") == []


def test_failure_mid_transaction_rolls_back_every_row(tmp_path, runs):
    reference, broken = runs
    db = tmp_path / "runs.sqlite"
    save_run(db, reference)
    broken["results"][1]["reply"]["text"] = object()  # JSON falha após a primeira inserção.
    with pytest.raises(TypeError):
        save_run(db, broken)
    assert [r["id"] for r in list_runs(db)] == [reference["id"]]
    with sqlite3.connect(db) as connection:
        assert connection.execute("SELECT COUNT(*) FROM results WHERE run_id = ?", (broken["id"],)).fetchone()[0] == 0


def test_missing_run_has_clear_error(tmp_path):
    with pytest.raises(ValueError, match="Execução não encontrada"):
        load_run(tmp_path / "empty.sqlite", "missing")
