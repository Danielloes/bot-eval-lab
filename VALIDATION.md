# Registro de validação

Este arquivo registra execuções reais desta entrega. Os comandos abaixo usam caminhos locais padrão para facilitar a reprodução; os IDs pertencem às execuções originais e novas execuções recebem novos IDs.

## Ambiente e testes

- Windows 11, Python **3.14.10**, pytest **9.2.0**.
- Instalação real com `python -m pip install -e ".[dev]"` em um ambiente virtual separado, sem torch, numpy ou sentence-transformers.
- `python -m pytest -q`, com `HF_HUB_OFFLINE=1` e `TRANSFORMERS_OFFLINE=1`: **49 passed in 4.65s**.
- A suíte cobre ranking estável, decisão, separação de rótulos, verificações independentes, regressões/melhorias/falhas compartilhadas, transação interrompida, comparações incompatíveis, fluxo da CLI, HTML escapado e códigos de saída.
- O teste do contrato semântico usa um double explicitamente identificado. O experimento abaixo usa o modelo real.
- O pacote wheel foi construído, instalado em diretório isolado e executado fora da árvore do projeto. A demo empacotada reproduziu 18/18 versus 16/18 e duas regressões críticas, confirmando que os JSONs estão incluídos no pacote.

## Demo offline final

```bash
python -m bot_eval_lab demo --output examples/demo.html
```

- Referência: `50b34de598f94b859e02592dd26c4bcd`.
- Candidata: `25e566856d264791a8b58c651939d5f8`.
- Dataset: `aurora-eval-v1`, divisão `holdout`, 18 casos; top-k = 4.
- Base: `aurora-fictional-policies-v1`, 11 trechos fictícios.
- Referência: **18/18** casos aprovados; candidata: **16/18**.
- Regressões: **C035 e C036**, ambas críticas, com ação errada, seleção de evidência errada e promessa proibida de reembolso.
- Melhorias: **0**; falhas nas duas: **0**.
- Seleção de evidência, tanto recuperada quanto usada: **12/12** versus **10/12**.
- Latência p50/p95: referência **0,0819 / 0,1571 ms**; candidata **0,0537 / 0,0824 ms**.

[HTML gerado](examples/demo.html) · [Resumo, configuração, hashes e verificações em JSON](examples/demo-summary.json).

O HTML foi aberto e inspecionado no navegador: métricas lado a lado, primeira conversa C035 com o selo “REGRESSÃO · CRÍTICO”, respostas distintas e falhas da candidata visíveis. O conteúdo `<script>` do caso C030 aparece como texto escapado.

### Códigos de saída observados

| Comparação com `--check` | Código |
| --- | ---: |
| Referência lexical → lexical defeituosa | 1 |
| Referência lexical → mesma execução lexical | 0 |
| Duas execuções lexicais independentes, no teste da CLI | 0 |
| Referência lexical → semântica real | 1 |
| Conjuntos incompatíveis, no teste da CLI | 2 |

O HTML é produzido antes do retorno 1. A demo comum, sem `--check`, retorna 0 mesmo quando encontra a regressão intencional.

## Experimento semântico real

```bash
python -m pip install '.[semantic]'
python -m bot_eval_lab experiment --cache-dir .cache/models --output examples/semantic.html
```

O modelo público foi baixado e carregado, sem chave, na CPU. Não houve substituição por embeddings fictícios, API remota de inferência ou resposta gerada por LLM.

| Configuração | Valor observado |
| --- | --- |
| Modelo | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` |
| Revisão | `bf3bf13ab40c3157080a7ab344c831b9ad18b5eb` |
| Dimensão / limite | 384 / 128 tokens |
| Normalização e ranking | vetores unitários; cosseno; top-4; empate por ID |
| sentence-transformers | 5.7.0 |
| transformers | 5.23.0 |
| torch | 2.15.0 |
| numpy | 2.5.5 |
| Referência | `f731ac77a49e46f58574bce1461484d7` |
| Candidata semântica | `ddff93fa95c246b498bac1d9fcba6afa` |

| Medida | Lexical | Semântica |
| --- | ---: | ---: |
| Casos aprovados | 18/18 (100%) | 11/18 (61,1%) |
| Acerto da ação | 18/18 (100%) | 12/18 (66,7%) |
| Ação `answer` | 6/6 | 0/6 |
| Ação `clarify` | 6/6 | 6/6 |
| Ação `handoff` | 6/6 | 6/6 |
| Seleção de evidência recuperada | 12/12 | 5/12 |
| Seleção de evidência usada | 12/12 | 5/12 |
| Falhas críticas | 0 | 1 |
| Latência p50 (ms) | 0,0635 | 12,2919 |
| Latência p95 (ms) | 0,1037 | 13,8417 |

**7 regressões, 1 crítica, 0 melhorias, 0 falhas compartilhadas.** O resultado foi pior que o lexical neste conjunto e configuração. Não houve ajuste de modelo, política, decisão, k ou rótulos para melhorar o placar depois de observar o holdout.

As regressões C003, C004, C009, C010, C013 e C014 ocorreram porque a política necessária para responder ficou fora do top-4, provocando `policy_missing` e `handoff`. No C046, `handoff` coincidiu com a ação esperada, mas a seleção da evidência falhou. O rótulo de criticidade do caso torna essa uma falha crítica mesmo sem promessa proibida. Nenhuma promessa indevida foi detectada nesta execução semântica.

Uma conferência adicional, sem rede e com `local_only=True`, carregou o modelo do cache e verificou **11 vetores de 384 dimensões**, todos finitos, com normas entre **0,99999994 e 1,00000012**. Consultar o texto exato de cada política recuperou a própria política em primeiro lugar em **11/11** consultas, com cosseno aproximadamente 1. Isso verifica integridade básica do cálculo e uso do cache, sem comprovar qualidade da busca com linguagem de clientes.

[HTML semântico real](examples/semantic.html) · [Resumo completo em JSON](examples/semantic-summary.json). As datas UTC, hashes, versões e configurações originais também aparecem nos relatórios.

## Limites do que foi validado

- O **GitHub Actions remoto não foi executado**, pois não foi criado nem publicado um repositório remoto. O workflow está configurado para Python 3.11/3.12 em Ubuntu e Windows; a validação local foi em Windows com Python 3.14.10.
- Linux e macOS não foram executados neste ambiente.
- Não há integração real com a Blip, dados de clientes ou operação comercial; o adaptador é uma proposta de evolução no README.
- Uma rodada de latências em 18 casos não permite inferir desempenho de produção. As duas referências lexicais das tabelas pertencem a execuções diferentes; seus tempos variam.
- Os exemplos são um registro local e sintético, não uma avaliação cega independente nem uma prova de qualidade geral do atendimento.
