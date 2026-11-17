import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from bot_eval_lab import cli
from bot_eval_lab.dataset import DATA
from bot_eval_lab.evaluation import compare_runs
from bot_eval_lab.report import render_report
from bot_eval_lab.storage import list_runs

ROOT = Path(__file__).resolve().parents[1]


def invoke(tmp_path, *arguments):
    env = {**os.environ, "PYTHONPATH": str(ROOT), "PYTHONUTF8": "1",
           "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"}
    return subprocess.run([sys.executable, "-m", "bot_eval_lab", *arguments],
                          cwd=tmp_path, env=env, capture_output=True, text=True,
                          encoding="utf-8", timeout=30)


def test_cli_full_flow_evaluate_compare_and_check(tmp_path):
    reference = invoke(tmp_path, "evaluate", "--strategy", "lexical", "--split", "dev")
    stable = invoke(tmp_path, "evaluate", "--strategy", "lexical", "--split", "dev")
    buggy = invoke(tmp_path, "evaluate", "--strategy", "lexical-buggy", "--split", "dev")
    for result in (reference, stable, buggy):
        assert result.returncode == 0, result.stderr
    ids = [json.loads(result.stdout)["run_id"] for result in (reference, stable, buggy)]
    good = invoke(tmp_path, "compare", ids[0], ids[1], "--check", "--output", "stable.html")
    bad = invoke(tmp_path, "compare", ids[0], ids[2], "--check", "--output", "regression.html")
    assert good.returncode == 0, good.stderr
    assert bad.returncode == 1, bad.stderr
    assert json.loads(bad.stdout)["critical_regressions"] >= 1
    html = (tmp_path / "regression.html").read_text(encoding="utf-8")
    assert "REGRESSÃO · CRÍTICO" in html and "reembolso automático" in html
    assert "Trechos usados" in html and "Trechos recuperados em ordem" in html
    assert len(list_runs(tmp_path / "reports/evaluations.sqlite")) == 3


def test_demo_offline_generates_report_and_critical_exit(tmp_path):
    result = invoke(tmp_path, "demo", "--split", "dev", "--check")
    assert result.returncode == 1, result.stderr
    assert (tmp_path / "reports/demo.html").is_file()
    assert len(list_runs(tmp_path / "reports/evaluations.sqlite")) == 2


def test_default_demo_is_a_successful_command_even_with_expected_regression(tmp_path):
    result = invoke(tmp_path, "demo", "--split", "dev")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["critical_regressions"] > 0


def test_incompatible_saved_sets_produce_actionable_error(tmp_path):
    first = invoke(tmp_path, "evaluate", "--split", "dev")
    data = json.loads((DATA / "cases.json").read_text(encoding="utf-8"))
    data["cases"] = data["cases"][1:]  # Remove um caso dev; não executa holdout.
    changed_cases = tmp_path / "changed-cases.json"
    changed_cases.write_text(json.dumps(data), encoding="utf-8")
    second = invoke(tmp_path, "evaluate", "--split", "dev", "--cases", str(changed_cases))
    result = invoke(tmp_path, "compare", json.loads(first.stdout)["run_id"], json.loads(second.stdout)["run_id"])
    assert result.returncode == 2
    assert "Conjuntos incompatíveis" in result.stderr
    assert not (tmp_path / "reports/comparison.html").exists()


def test_html_escapes_untrusted_content_and_keeps_critical_regressions_first(runs):
    reference, candidate = runs
    for run in (reference, candidate):
        run["results"][0]["case"]["history"][0]["text"] = '<script>alert("x")</script>'
        run["results"][0]["reply"]["text"] = '<img src=x onerror="alert(1)">'
        run["results"][0]["reply"]["retrieved"][0]["policy"]["text"] = "<iframe>unsafe</iframe>"
    comparison = compare_runs(reference, candidate)
    html = render_report(comparison)
    assert "<script>" not in html and "<img src=x" not in html and "<iframe>" not in html
    assert "&lt;script&gt;" in html and "&lt;img" in html and "&lt;iframe&gt;" in html
    assert "<script src=" not in html and "<link " not in html
    first_id = comparison["pairs"][0]["id"]
    assert comparison["pairs"][0]["status"] == "regression"
    assert f'id="{first_id}"' in html


def test_cli_failed_execution_leaves_no_comparable_run(tmp_path, monkeypatch):
    class BrokenRetriever:
        config = {"strategy": "broken"}

        def __init__(self):
            self.calls = 0

        def search(self, query, k):
            self.calls += 1
            if self.calls >= 3:
                raise RuntimeError("falha simulada no segundo caso")
            return ()

    monkeypatch.setattr(cli, "make_retriever", lambda *a, **kw: BrokenRetriever())
    db = tmp_path / "runs.sqlite"
    assert cli.main(["evaluate", "--db", str(db), "--split", "dev"]) == 2
    assert list_runs(db) == []


def test_invalid_top_k_fails_without_saved_run(tmp_path):
    result = invoke(tmp_path, "evaluate", "--top-k", "0")
    assert result.returncode == 2 and "top_k" in result.stderr
    assert list_runs(tmp_path / "reports/evaluations.sqlite") == []
