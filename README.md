# Hanoi AI Lab

Laboratório pequeno para investigar uma pergunta simples: **contexto externo (RAG) e decomposição de tarefas ajudam um LLM local a resolver a Torre de Hanói?**

O projeto usa apenas Python, Ollama, `qwen2.5:3b`, `nomic-embed-text` e MySQL. Não há LangChain, agentes, API REST nem interface gráfica.

## Estratégias

O laboratório compara três estratégias separadas. Os resultados de uma não são misturados com os das outras.

1. **`baseline`** — uma chamada ao modelo, sem contexto externo.
2. **`rag`** — uma chamada com os trechos mais relevantes de `knowledge/`.
3. **`blocos`** — decomposição determinística em três etapas (bloco 1, disco maior, bloco 2). O modelo escolhe **um movimento por chamada** dentro de cada etapa; o estado é carregado, o alvo do bloco é conferido e a tentativa para no primeiro erro.

O validador é Python puro e independente do modelo: ele simula cada movimento em três pinos e o laboratório só marca `resolveu` quando a torre inteira está em C, na ordem correta. O modelo nunca é acreditado pela própria resposta.

## Tecnologias

- Python 3.10+
- Ollama com `qwen2.5:3b` e `nomic-embed-text`
- MySQL 8
- `requests` e `mysql-connector-python`

## Como funciona

```
hanoi_eval.py  ->  monta o prompt e chama o Ollama
validator.py   ->  simula os movimentos e decide se resolveu
rag.py         ->  divide knowledge/, gera embeddings e busca por cosseno
database.py    ->  cria as tabelas e grava execuções/resultados
config.py      ->  modelo, discos, repetições, temperatura, seeds e URLs
```

Cada chamada ao modelo é registrada em `resultados`, inclusive timeout, modelo ausente e falha de conexão. O prompt, a resposta bruta, o estado final, a seed, a temperatura e os chunks recuperados ficam no banco.

## Como executar

Pré-requisitos: Python 3.10+, Ollama com os dois modelos e MySQL 8.

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # Linux/macOS
pip install -r requirements.txt
```

Crie o banco (exemplo com Docker; use sua própria senha):

```bash
docker run -d --name mysql-hanoi \
  -e MYSQL_ROOT_PASSWORD=change-me \
  -e MYSQL_DATABASE=hanoi \
  -p 3306:3306 mysql:8
```

Configure o `.env`:

```bash
copy .env.example .env          # Windows
cp .env.example .env            # Linux/macOS
```

Rode uma estratégia por vez:

```bash
python hanoi_eval.py --estrategia baseline --discos 3 --repeticoes 10
python hanoi_eval.py --estrategia rag      --discos 3 --repeticoes 10
python hanoi_eval.py --estrategia blocos   --discos 3 --repeticoes 10
```

Para 4 discos, troque `--discos 3` por `--discos 4`. O RAG indexa `knowledge/` na primeira execução.

Testes:

```bash
python -m unittest discover -s tests -t . -v
```

## Resultados históricos (antes da simplificação)

O banco preserva 47 execuções e 388 registros históricos (`v1` a `v4`, ids 1–47), além de cinco execuções de fumaça do código novo. O resumo honesto do laboratório anterior:

| Evidência | Resultado |
|---|---:|
| Registros de 4 discos | 173 |
| Acertos em 4 discos | **0** |
| Respostas válidas de v4a/v4b com o mesmo estado final errado `A=[] B=[3,2] C=[4,1]` | 11 de 13 |
| Erros no lance 10 (“pino A vazio”) em v4a/v4b | 11 de 13 |
| Controle de cópia R4 em 3 discos | 10/10, uma única resposta (gabarito) |
| Single-shot `v2` em 3 discos, sem o R4 | 6/80 nominais, mas só **2 respostas distintas corretas** |
| `formato_invalido` no parser | 0 |

Interpretação: o modelo consegue reproduzir a solução de 3 discos e às vezes o bloco 1 + o lance do meio, mas **repete o padrão do bloco 1** em vez de executar o bloco 2 com as hastes trocadas. O RAG antigo recuperava o conteúdo certo, mas o corpus tinha gabaritos literais; o modelo copiava o gabarito (R4 10/10), não raciocinava. O gargalo é composição/troca de papéis, não o parser.

Os números antigos **não são diretamente comparáveis** com os novos: o laboratório anterior usou temperaturas, seeds e corpora diferentes, e parte das execuções sofreu pseudo-replicação. O código novo usa temperatura 0,5, seeds fixas `1000..`, prompt `v5` e um corpus sem gabaritos.

Detalhes em [docs/EXPERIMENTOS.md](docs/EXPERIMENTOS.md).

> No PowerShell 5.1, acentos podem aparecer trocados no terminal. Use Windows Terminal ou `chcp 65001`; os textos no banco e nos arquivos estão em UTF-8.

## Estrutura

```
hanoi_eval.py        # execução das três estratégias
validator.py         # parser + simulação determinística
rag.py               # chunking, embeddings e busca por cosseno
database.py          # conexão e persistência
config.py            # configurações
knowledge/           # regras, estratégia recursiva e composição
docs/                # arquitetura, experimentos e estudos
tests/               # testes automatizados
```

## Limitações

- Um modelo pequeno (3B), uma tarefa e `n=10` por condição.
- A temperatura 0,5 gera amostras diferentes, mas o n efetivo pode ser menor que 10; reporte respostas distintas.
- Não há controle positivo com modelo maior ou solver determinístico.
- 4 discos é o teste honesto; 3 discos é fácil e pode ser memorizado.
- O RAG novo mede conhecimento procedural, não cópia de gabarito.

## Documentação

- [docs/ARQUITETURA.md](docs/ARQUITETURA.md) — como o laboratório funciona.
- [docs/EXPERIMENTOS.md](docs/EXPERIMENTOS.md) — estratégias, métricas e resultados.
- [docs/ESTUDOS.md](docs/ESTUDOS.md) — conceitos para estudar e explicar o projeto.
