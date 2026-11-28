# Arquitetura

## Visão geral

O laboratório tem uma única porta de entrada (`hanoi_eval.py`) e três estratégias. O fluxo é sempre:

```
CLI -> config -> MySQL -> checagem do Ollama -> (RAG opcional) -> execução -> validador -> MySQL -> resumo
```

Nada acredita na resposta do modelo. A decisão de sucesso é sempre determinística, feita pelo estado simulado pelo `validator.py` e conferida pelo runner.

## Arquivos e responsabilidades

| Arquivo | Responsabilidade |
|---|---|
| `hanoi_eval.py` | CLI, prompts, estratégias, chamadas ao Ollama, resumo |
| `validator.py` | extração de movimentos, simulação e validação determinística |
| `rag.py` | leitura de `knowledge/`, chunking, embeddings e busca por cosseno |
| `database.py` | conexão MySQL, criação aditiva das tabelas e persistência |
| `config.py` | modelo, discos, repetições, temperatura, seeds, URLs e caminhos |
| `knowledge/` | regras, estratégia recursiva e composição (sem gabaritos) |
| `tests/` | testes de validador, RAG, banco e tratamento de falhas |

## Estratégias

### `baseline`

Uma chamada com o prompt base. O modelo devolve a sequência completa. O validador simula do estado inicial.

### `rag`

Igual ao baseline, mas o prompt recebe os `TOP_K` trechos mais parecidos de `knowledge/`. A consulta é fixa por número de discos: “mover N discos da haste A para a haste C usando B como auxiliar”.

O corpus novo tem apenas regras, estratégia recursiva e composição. Não há gabaritos de 3 ou 4 discos, para não confundir “RAG” com “copiar resposta”.

### `blocos`

A decomposição é determinística:

```
N discos de X para Y =
    (N-1 discos de X para Z)
  + (disco N de X para Y)
  + (N-1 discos de Z para Y)
```

Para 4 discos, são três etapas (3 discos de A para B, disco 4 de A para C, 3 discos de B para C). Em cada etapa, o modelo recebe o estado atual e o objetivo do bloco, e escolhe **um movimento por chamada**. O laboratório aplica o movimento, atualiza o estado e repete até o estado-alvo do bloco ou até o limite de chamadas (`mínimo do bloco + 2`).

O estado-alvo é calculado com o plano mínimo determinístico. O modelo **não** recebe os blocos prontos: ele decide cada movimento. Se o estado obtido não for o alvo dentro do limite, a tentativa falha com `torre_incompleta`. Se o modelo resolver a torre antes do fim, a tentativa é sucesso.

## Validador

O parser aceita:

- um ou mais movimentos por linha;
- `A->C`, `A=>C`, `A→C` e variações com espaços;
- numeração, bullets, “Passo N:” e anotações como “(disco 1)”, “#2” e “2 movimentos”.

Ele rejeita texto com seta que não seja movimento (por exemplo, “O disco 1 vai de A->C porque sim”) e rejeita a cadeia ambígua `A->B->C`.

A simulação usa três listas, da base para o topo. Um movimento para a mesma haste não conta. `movimentos` no resultado é o número de movimentos **aplicados antes do primeiro erro**, não o número de movimentos encontrados no texto.

Status possíveis:

- `ok`: a chamada foi legal (no baseline/RAG, a torre inteira; nos blocos, o movimento foi aplicado).
- `lance_ilegal`: pino vazio ou disco maior sobre menor.
- `torre_incompleta`: movimentos legais, mas o alvo não foi atingido; nos blocos, é a linha sintética gravada quando o limite de chamadas acaba.
- `formato_invalido`: nenhum movimento reconhecido.

## Banco de dados

Tabelas:

- `execucoes`: uma linha por execução (modelo, discos, repetições, modo, versão do prompt, versão do corpus, digest do modelo).
- `resultados`: uma linha por chamada ao modelo.
- `rag_trechos`: cache de chunks e embeddings.

Campos importantes de `resultados`:

| Campo | Significado |
|---|---|
| `tentativa` | número da repetição (1..N) |
| `rodada` | 1 no baseline/RAG; 1..3 nos blocos (uma linha por movimento) |
| `resolveu` | a torre inteira está em C? Só pode ser verdadeiro na chamada que fecha o problema |
| `status` | resultado da chamada (ver acima) |
| `movimentos_feitos` | movimentos aplicados naquela chamada (nos blocos, normalmente 1) |
| `movimentos_minimos` | mínimo global `2^N - 1` |
| `estado_final` | JSON do estado depois da chamada |
| `chunks` | JSON com documento/score dos trechos usados (NULL sem RAG) |
| `prompt`, `resposta_bruta` | texto exato enviado e recebido |
| `temperatura`, `seed` | parâmetros de amostragem |
| `usou_rag`, `usou_memoria` | flags de contexto |

`chunks_rag` é uma coluna legada do laboratório antigo; o código novo grava apenas `chunks`.

Chunks de corpora antigos podem permanecer em `rag_trechos`; `rag.buscar` filtra pelos hashes dos documentos atuais, então eles não entram no contexto. Isso preserva o histórico e evita uma migração destrutiva.

As migrações são aditivas (`ALTER TABLE ... ADD COLUMN`), nunca destrutivas. O histórico antigo permanece.

## Reprodutibilidade

Cada execução registra:

- modelo fixo `qwen2.5:3b`;
- temperatura 0,5;
- seeds `1000..1000+N-1`;
- prompt `v5`;
- versão do corpus (hash curto dos documentos);
- digest exato do modelo no Ollama;
- prompt e resposta brutos;
- estado final e chunks.

A temperatura 0,5 é uma escolha explícita: com temperatura 0, repetir N vezes produziria a mesma resposta e inflaria o n. As seeds fixas tornam as amostras reproduzíveis. O custo é que os resultados novos não são diretamente comparáveis com execuções antigas em temperatura 0.

## Tratamento de falhas

`chamar_ollama` traduz os erros:

| Falha | Status | Fatal? |
|---|---|---|
| conexão recusada | `erro_ollama` | sim |
| timeout de leitura | `timeout` | não |
| HTTP 404 | `modelo_ausente` | sim |
| outro HTTP | `http_erro` | não |
| outra falha de requests | `erro_ollama` | não |

Falhas não fatais são gravadas e a próxima tentativa continua. Falhas fatais são gravadas e interrompem a execução. Em todos os casos, `chunks` vai para a coluna `chunks`; nunca para `estado_final`.

## Testes

Os testes não dependem de MySQL nem de Ollama:

- `test_validator.py`: parser, estados, erros, contagem de movimentos aplicados, estado carregado.
- `test_rag.py`: chunking, cosseno, ranking, busca com hash atual, indexação e versão do corpus.
- `test_database.py`: mapeamento de parâmetros, `discos` explícito, chunks no campo certo, campos opcionais.
- `test_hanoi_eval.py`: decomposição, plano, prompts, estratégia de blocos, sucesso/falha, tradução de erros do Ollama e regressão do bug de `chunks_info`.

Execute com:

```bash
python -m unittest discover -s tests -t . -v
```
