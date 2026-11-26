# hanoi-eval

A small lab to test local LLMs on the Tower of Hanoi.

## What is this?

A **lab**, not a production app: an exploratory experiment to learn how to
evaluate small local models in a reproducible way.

## Research question

Do prompt strategies (baseline, error memory, RAG) help a small local model
solve a recursive planning task?

## How it works

The project has four layers:

1. **Evaluation** - `hanoi_eval.py` sends prompts to a local Ollama model
   (temperature 0) and repeats the test N times.
2. **Deterministic validation** - `validar()` simulates the moves on 3 pegs
   and only accepts a full, ordered tower on peg C. It never trusts the model.
3. **Observability** - every run and attempt is logged in MySQL (`execucoes`,
   `resultados`): accuracy, moves, error, latency, status, prompt, raw answer,
   final peg state, retrieved chunks and model digest. Failed calls are logged
   too, never skipped.
4. **Custom RAG** - `rag.py` chunks the markdown files, embeds them with
   `nomic-embed-text`, stores them in MySQL and retrieves the top-k chunks by
   cosine similarity.

## The 3 prompt strategies

All modes share the same base prompt (task, planning guidance, output format);
the treatment only adds context.

- **Baseline** - base prompt only.
- **Error memory** - adds the last stored errors for the same model and disk
  count, asking the model not to repeat them.
- **RAG** - adds knowledge retrieved from `knowledge/`.

Toggle them with `USAR_MEMORIA` and `USAR_RAG` at the top of `hanoi_eval.py`
(RAG is on by default). RAG indexing runs automatically on the first run with
`USAR_RAG = True`. Prompt changes bump `VERSAO_PROMPT`, stored per run in
`execucoes.prompt_versao`.

## Results so far (honest summary)

- 16 runs and 55 stored attempts, all with `qwen2.5:3b` (prompt `v1`).
- Baseline (22 attempts): 0 successes; every stored attempt fails at move 6.
- RAG (32 attempts): 0 successes; 20 end with an incomplete tower, 12 include
  an illegal move.
- Memory (1 attempt): one success; single sample, not conclusive.
- No strategy can be said to "work" yet. Runs under prompt `v2` are tracked
  separately by `prompt_versao`.

## Limitations and next steps

- Small models only (3B), one task. Raw answers are stored from prompt `v2` on.
- The `v1` runs have no raw answers; memory mode was tested only once.
- Old RAG embeddings may stay in the DB.
- Next: run A/B tests with 10+ repetitions under prompt `v2`, try more models,
  and clean stale RAG embeddings.

## Privacy note

Models, database data and local files are **not** in this repo. Everything
runs locally on the machine of whoever executes it.

## How to run

Prerequisites: Python 3.8+, Ollama with `qwen2.5:3b` (and `nomic-embed-text`
for RAG) and MySQL 8.

Install and activate the venv:

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # Linux/macOS
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Create the database (example with Docker; use your own password):

```bash
docker run -d --name mysql-hanoi -e MYSQL_ROOT_PASSWORD=change-me -e MYSQL_DATABASE=hanoi -p 3306:3306 mysql:8
```

Configure and run:

```bash
copy .env.example .env        # Windows; on Linux/macOS: cp .env.example .env
python hanoi_eval.py
```

Tables are created automatically, and existing databases are migrated with
additive changes only. Set `USAR_RAG = True` to index `knowledge/` and use RAG.

Run the validator tests:

```bash
python -m unittest discover -s tests -t . -v
```

## Project structure

```
hanoi_eval.py        # evaluation loop, prompt modes, validation, MySQL logging
rag.py               # custom RAG: chunking, embeddings, cosine search
knowledge/           # markdown docs used by the RAG
tests/               # unit tests for the validator
requirements.txt     # dependencies
.env.example         # example env vars
README.md            # this file
```

## Status

Exploratory study, work in progress.
