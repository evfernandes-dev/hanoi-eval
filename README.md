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
   `resultados`): accuracy, moves, error, latency and mode.
4. **Custom RAG** - `rag.py` chunks the markdown files, embeds them with
   `nomic-embed-text`, stores them in MySQL and retrieves the top-k chunks by
   cosine similarity.

## The 3 prompt strategies

- **Baseline** - rules + output format only.
- **Error memory** - adds the last stored errors for the same model and disk
  count, asking the model not to repeat them.
- **RAG** - adds knowledge retrieved from `knowledge/`.

Toggle them with `USAR_MEMORIA` and `USAR_RAG` at the top of `hanoi_eval.py`.
RAG indexing runs automatically on the first run with `USAR_RAG = True`.

## Results so far (honest summary)

- 14 runs and 45 attempts, mostly with `qwen2.5:3b`.
- Baseline fails at move 6 every time.
- One memory-mode run solved it once: single sample, not conclusive.
- RAG makes the moves legal (7 moves), but the tower still ends incomplete.
- No strategy can be said to "work" yet.

## Limitations and next steps

- Small models only (3B), one task, raw answers not saved yet.
- Memory mode was tested only once; old RAG embeddings may stay in the DB.
- Next: save raw answers, run A/B tests with 10+ repetitions, try more models.

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

Tables are created automatically. Set `USAR_RAG = True` to index `knowledge/`
and use RAG.

## Project structure

```
hanoi_eval.py        # evaluation loop, prompt modes, validation, MySQL logging
rag.py               # custom RAG: chunking, embeddings, cosine search
knowledge/           # markdown docs used by the RAG
requirements.txt     # dependencies
.env.example         # example env vars
README.md            # this file
```

## Status

Exploratory study, work in progress.
