"""HTML autocontido: sem JavaScript, CDN, fontes remotas ou dados não escapados."""

import json
import os
import tempfile
from html import escape
from pathlib import Path

LABELS = {"regression": "REGRESSÃO", "improvement": "MELHORIA",
          "both_pass": "PASSOU NAS DUAS", "both_fail": "FALHOU NAS DUAS"}


def esc(value) -> str:
    return escape(str(value), quote=True)


def fraction(value: dict) -> str:
    return f"{value['passed']}/{value['total']} · {value['rate']:.1%}" if value["total"] else "Não aplicável · 0/0"


def metrics_table(reference: dict, candidate: dict) -> str:
    rows = []
    specs = [("Casos aprovados (todos os critérios)", "passed"), ("Acerto da ação — geral", "action"),
             ("Seleção da evidência esperada — recuperada", "evidence_retrieved"),
             ("Seleção da evidência esperada — usada", "evidence_used")]
    for label, key in specs:
        rows.append(f"<tr><th>{label}</th><td>{fraction(reference[key])}</td><td>{fraction(candidate[key])}</td></tr>")
    for action in ("answer", "clarify", "handoff"):
        rows.append(f"<tr><th>Acerto da ação — {action}</th><td>{fraction(reference['by_action'][action])}</td><td>{fraction(candidate['by_action'][action])}</td></tr>")
    for label, key in [("Falhas críticas", "critical_failures"), ("Latência p50 (ms)", "p50_ms"), ("Latência p95 (ms)", "p95_ms")]:
        values = [str(run[key]) if key == "critical_failures" else f"{run[key]:.3f}" for run in (reference, candidate)]
        rows.append(f"<tr><th>{label}</th><td>{values[0]}</td><td>{values[1]}</td></tr>")
    return '<div class="table-scroll"><table><thead><tr><th>Métrica</th><th>Referência</th><th>Candidata</th></tr></thead><tbody>' + "".join(rows) + "</tbody></table></div>"


def result_column(result: dict, label: str) -> str:
    reply, checks = result["reply"], result["checks"]
    hits = "".join(f'<li><strong>{esc(h["policy"]["id"])} · {esc(h["policy"]["title"])}</strong> <span class="muted">score {h["score"]:.4f}</span><p>{esc(h["policy"]["text"])}</p></li>' for h in reply["retrieved"])
    used = ", ".join(esc(p) for p in reply["used"]) or "Nenhum"
    status = "PASSOU" if checks["passed"] else "FALHOU"
    detail = "".join(f"<li>{esc(reason)}</li>" for reason in checks["failure_reasons"]) or "<li>Todos os critérios atendidos.</li>"
    check_labels = " · ".join(f"{name}: {'OK' if checks[key] else 'FALHA'}" for name, key in [("Ação", "action_ok"), ("Evidência usada", "evidence_ok"), ("Comportamento", "behavior_ok")])
    return f'''<section class="version"><h4>{esc(label)} <span class="badge">{status}</span></h4>
    <p><strong>Ação:</strong> {esc(reply['action'])} · <strong>Motivo:</strong> {esc(reply['reason'])}</p>
    <blockquote>{esc(reply['text'])}</blockquote><p class="checks">{check_labels}</p><ul>{detail}</ul>
    <p><strong>Trechos usados:</strong> {used}</p>
    <details><summary>Trechos recuperados em ordem ({len(reply['retrieved'])})</summary><ol>{hits}</ol></details>
    <p class="muted">Execução do assistente: {result['latency_ms']:.3f} ms</p></section>'''


def case_card(pair: dict) -> str:
    case = pair["reference"]["case"]
    history = "".join(f'<li><strong>{"Cliente" if m["role"] == "user" else "Assistente anterior"}</strong><p>{esc(m["text"])}</p></li>' for m in case["history"])
    critical = " · CRÍTICO" if pair["critical"] else ""
    accepted = ", ".join(esc(p) for p in case["expected_evidence"]) or "Sem evidência exigida (validação de contexto/escopo)"
    forbidden = ", ".join(esc(v) for v in case["forbidden"]) or "Nenhum comportamento específico cadastrado"
    return f'''<article class="case {pair['status']}" id="{esc(pair['id'])}">
    <div class="case-top"><span class="badge">{LABELS[pair['status']]}{critical}</span><span>{esc(case['id'])} · {esc(case['category'])}</span></div>
    <h3>{esc(case['description'])}</h3><p class="muted">Grupo: {esc(case['group'])} · Divisão: {esc(case['split'])}</p>
    <div class="context"><div><h4>Conversa</h4><ol class="conversation">{history}</ol></div>
    <div><h4>Comportamento esperado</h4><p><strong>{esc(case['expected_action'])}</strong> — {esc(case['expected_behavior'])}</p>
    <p><strong>Evidência aceita ({esc(case['evidence_mode'])}):</strong> {accepted}</p><p><strong>Proibido:</strong> {forbidden}</p></div></div>
    <div class="versions">{result_column(pair['reference'], 'Referência')}{result_column(pair['candidate'], 'Candidata')}</div></article>'''


CSS = """
:root{color-scheme:light;--ink:#172b35;--muted:#526874;--line:#d3dee0;--paper:#f3f6f5;--teal:#006d68}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.6 system-ui,-apple-system,Segoe UI,sans-serif}
main{max-width:1240px;margin:auto;padding:40px 24px 80px}header{padding:34px;background:#123b43;color:#fff;border-radius:16px}
h1{font-size:clamp(2.2rem,5vw,3.4rem);margin:0;letter-spacing:-.04em}h2{margin-top:40px}h3{line-height:1.35;font-size:1.25rem}h4{margin:0 0 12px}
.eyebrow{letter-spacing:.13em;text-transform:uppercase;font-size:.78rem;font-weight:700;color:#a5e5d1}.muted{color:var(--muted);font-size:.88rem}
header .muted{color:#c3dadd}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:24px 0}.stat{background:white;border:1px solid var(--line);border-radius:10px;padding:18px}.stat b{display:block;font-size:2rem;line-height:1.3}.stat.alert{border-top:4px solid #bc3d2d}
.table-scroll{overflow-x:auto}table{border-collapse:collapse;width:100%;background:white}th,td{padding:12px 16px;border-bottom:1px solid var(--line);text-align:left}thead{background:#dcebe7}th{font-weight:600}td{font-variant-numeric:tabular-nums}
.notice{background:#e2eeeb;border-left:4px solid var(--teal);padding:14px 20px;margin:20px 0}.case{background:white;border:1px solid var(--line);border-radius:12px;margin:24px 0;overflow:hidden;padding:24px;scroll-margin-top:24px}.case.regression{border-top:5px solid #bc3d2d}.case.both_fail{border-top:5px solid #9a6a15}.case.improvement{border-top:5px solid #007b63}.case-top{display:flex;gap:16px;justify-content:space-between;flex-wrap:wrap;font-size:.85rem}
.badge{display:inline-block;border-radius:5px;background:#edf0f1;font-weight:700;padding:3px 9px;font-size:.75rem}.regression>.case-top .badge{background:#ffe3dd;color:#8c2318}.context,.versions{display:grid;grid-template-columns:1fr 1fr;gap:24px}.context{border-block:1px solid var(--line);padding:20px 0;margin:20px 0}.version{min-width:0}.version+.version{border-left:1px solid var(--line);padding-left:24px}blockquote{margin:0;background:#f0f6f4;padding:16px;border-left:3px solid var(--teal);white-space:pre-wrap}.conversation{padding-left:24px}.conversation p{margin:3px 0 12px;white-space:pre-wrap}.checks{font-size:.85rem;font-weight:600}details{margin:12px 0}summary{cursor:pointer;font-weight:600;color:var(--teal)}li p{margin-top:4px}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:white;padding:16px;border:1px solid var(--line);font-size:.8rem}a{color:var(--teal)}nav{display:flex;flex-wrap:wrap;gap:8px}nav a{padding:4px 10px;border:1px solid var(--line);border-radius:6px;background:white}.method{font-size:.9rem}footer{margin-top:32px;font-size:.85rem;color:var(--muted)}
@media(max-width:760px){main{padding:20px 12px}.stats{grid-template-columns:1fr 1fr}.context,.versions{grid-template-columns:1fr}.version+.version{border-left:0;border-top:1px solid var(--line);padding:20px 0 0}.case{padding:18px}header{padding:24px}th,td{padding:10px}}
@media print{body{background:white}main{padding:0}details{display:block}.case{break-inside:avoid}nav{display:none}}
"""


def render_report(comparison: dict) -> str:
    ref, cand = comparison["reference"], comparison["candidate"]
    nav = "".join(f'<a href="#{esc(p["id"])}">{esc(p["id"])} · {LABELS[p["status"]]}</a>' for p in comparison["pairs"] if p["status"] != "both_pass")
    metadata = {label: {k: run[k] for k in ("id", "created_at", "assistant_version", "evaluator_version", "dataset_hash", "policy_hash", "config")} for label, run in [("reference", ref), ("candidate", cand)]}
    policy_note = "Bases de políticas diferentes; compare também as revisões dos trechos." if ref["policy_hash"] != cand["policy_hash"] else "Mesma base de políticas nas duas execuções."
    return f'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'">
    <title>Bot Eval Lab — Comparação de assistentes</title><style>{CSS}</style></head><body><main>
    <header><div class="eyebrow">Laboratório de qualidade · loja e dados fictícios</div><h1>Bot Eval Lab</h1>
    <p>Uma atualização mudou o atendimento. Veja onde, por quê e com qual evidência.</p>
    <p class="muted">{esc(ref['config']['strategy'])} → {esc(cand['config']['strategy'])} · {len(comparison['pairs'])} conversas · divisão {esc(ref['dataset']['split'])}</p></header>
    <div class="stats"><div class="stat alert"><b>{comparison['critical_regressions']}</b>Regressões críticas</div><div class="stat"><b>{comparison['regressions']}</b>Regressões totais</div><div class="stat"><b>{comparison['improvements']}</b>Melhorias</div><div class="stat"><b>{comparison['both_fail']}</b>Falhas nas duas versões</div></div>
    <p class="notice">Uma conversa passa quando a ação está correta, a seleção da evidência usada atende à regra do caso e nenhum comportamento proibido é detectado. Acertar apenas a ação não basta.</p>
    <h2>Resultado lado a lado</h2>{metrics_table(ref['metrics'], cand['metrics'])}
    <p class="method">Seleção da evidência: casos com IDs esperados atendidos / casos com evidência esperada. Regra <code>all</code>: todos os IDs; <code>any</code>: ao menos um. Casos sem evidência esperada ficam fora dos denominadores. Esta métrica não julga a qualidade ou a fundamentação semântica do texto.</p>
    <p class="method">Latência: uma amostra por conversa, após carregar o modelo, indexar políticas e aquecer com uma consulta fixa. Inclui preparação da consulta, busca (embedding quando aplicável), decisão e resposta. Exclui avaliação, banco e HTML. Percentil nearest-rank: posição ceil(p × n), com p em [0,1]. Amostra pequena; não é benchmark de produção.</p>
    <h2>Conversas e diagnóstico</h2><p>Regressões críticas primeiro. Falhas já presentes na referência continuam visíveis.</p><nav aria-label="Casos com mudança ou falha">{nav or 'Nenhuma mudança ou falha.'}</nav>
    {''.join(case_card(p) for p in comparison['pairs'])}
    <h2>Reprodução e rastreabilidade</h2><p>{policy_note} Dataset: {esc(ref['dataset']['id'])} · base de referência: {esc(ref['corpus']['id'])}.</p>
    <details><summary>IDs, hashes, versões e configuração completa</summary><pre>{esc(json.dumps(metadata, ensure_ascii=False, indent=2))}</pre></details>
    <p class="method">Comportamentos proibidos: expressões regulares sobre texto sem acentos e em minúsculas detectam padrões explícitos de promessa de reembolso e confirmação de cancelamento. Não cobrem toda paráfrase ou negação do português. Não há juiz LLM.</p>
    <footer>Dados fictícios · respostas determinísticas · nenhuma integração ou vínculo oficial com a Blip · nenhuma operação comercial é executada.</footer>
    </main></body></html>'''


def write_report(path: Path, comparison: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    html = render_report(comparison)
    # Substituição atômica: um erro não deixa um HTML pela metade.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, suffix=".tmp", delete=False) as file:
            temporary = file.name
            file.write(html)
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)
