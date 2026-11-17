"""CLI pequena; execute `python -m bot_eval_lab --help`."""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

from .dataset import DATA, load_inputs
from .decision import Assistant
from .evaluation import compare_runs
from .report import write_report
from .retrieval import DEFAULT_MODEL, DEFAULT_REVISION, make_retriever
from .runner import evaluate
from .storage import list_runs, load_run, save_run


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Bot Eval Lab — loja e dados fictícios; avaliação local de atendimento")
    commands = root.add_subparsers(dest="command", required=True)
    for name, help_text in [("demo", "Comparar lexical com candidata defeituosa, sem rede"),
                            ("evaluate", "Avaliar uma estratégia e salvar no SQLite"),
                            ("experiment", "Comparar lexical com embeddings reais")]:
        command = commands.add_parser(name, help=help_text)
        command.add_argument("--db", type=Path, default=Path("reports/evaluations.sqlite"))
        command.add_argument("--split", choices=["dev", "holdout", "all"], default="holdout")
        command.add_argument("--cases", type=Path, default=DATA / "cases.json")
        command.add_argument("--policies", type=Path, default=DATA / "policies.json")
        command.add_argument("--top-k", type=int, default=4)
        if name == "evaluate":
            command.add_argument("--strategy", choices=["lexical", "lexical-buggy", "semantic"], default="lexical")
        else:
            command.add_argument("--output", type=Path, default=Path(f"reports/{'demo' if name == 'demo' else 'semantic'}.html"))
            command.add_argument("--check", action="store_true", help="Sair com código 1 se houver regressão crítica")
        if name != "demo":
            command.add_argument("--model", default=DEFAULT_MODEL)
            command.add_argument("--revision", default=DEFAULT_REVISION,
                                 help="Commit do modelo; ao trocar --model, informe também sua revisão")
            command.add_argument("--cache-dir", default=".cache/models")
            command.add_argument("--local-only", action="store_true", help="Proibir download; usar somente modelo já em cache")
    command = commands.add_parser("compare", help="Comparar duas execuções completas já salvas")
    command.add_argument("reference")
    command.add_argument("candidate")
    command.add_argument("--db", type=Path, default=Path("reports/evaluations.sqlite"))
    command.add_argument("--output", type=Path, default=Path("reports/comparison.html"))
    command.add_argument("--check", action="store_true")
    command = commands.add_parser("runs", help="Listar IDs das execuções salvas")
    command.add_argument("--db", type=Path, default=Path("reports/evaluations.sqlite"))
    return root


def run_strategy(args, strategy: str) -> dict:
    dataset, corpus, policies = load_inputs(args.cases, args.policies, args.split)
    options = {key: getattr(args, key) for key in ("revision", "cache_dir") if hasattr(args, key)}
    if hasattr(args, "model"):
        options["model_name"] = args.model
        options["local_only"] = args.local_only
    retriever = make_retriever(strategy, policies, **options)
    run = evaluate(Assistant(retriever, args.top_k), dataset, corpus)
    save_run(args.db, run)
    return run


def emit(value) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "evaluate":
            run = run_strategy(args, args.strategy)
            emit({"run_id": run["id"], "strategy": args.strategy, "split": args.split,
                  "db": str(args.db.resolve()), "metrics": run["metrics"]})
            return 0
        if args.command == "runs":
            emit([{key: run[key] for key in ("id", "created_at", "config", "dataset_hash", "metrics")} for run in list_runs(args.db)])
            return 0
        if args.command == "compare":
            reference = load_run(args.db, args.reference)
            candidate = load_run(args.db, args.candidate)
        else:
            reference = run_strategy(args, "lexical")
            candidate = run_strategy(args, "lexical-buggy" if args.command == "demo" else "semantic")
        comparison = compare_runs(reference, candidate)
        write_report(args.output, comparison)
        emit({"reference_id": reference["id"], "candidate_id": candidate["id"],
              "report": str(args.output.resolve()), "split": reference["dataset"]["split"],
              "reference_metrics": reference["metrics"], "candidate_metrics": candidate["metrics"],
              **{key: comparison[key] for key in ("regressions", "critical_regressions", "improvements", "both_fail")}})
        return 1 if args.check and comparison["critical_regressions"] else 0
    except (ValueError, KeyError, OSError, RuntimeError, sqlite3.Error) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
