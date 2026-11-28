"""Configurações do Hanoi AI Lab."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

MODELO = "qwen2.5:3b"
MODELO_EMBEDDING = "nomic-embed-text"

DISCOS_PADRAO = 3
REPETICOES_PADRAO = 10
TEMPERATURA = 0.5
SEED_BASE = 1000

TOP_K = 3
PASTA_CONHECIMENTO = BASE_DIR / "knowledge"

VERSAO_PROMPT = "v5"

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_TAGS_URL = "http://localhost:11434/api/tags"
OLLAMA_EMBED_URL = "http://localhost:11434/api/embed"
TIMEOUT_GERACAO = 180
TIMEOUT_EMBEDDING = 120


def carregar_env():
    """Lê o .env sem sobrescrever variáveis já definidas no sistema."""
    caminho = BASE_DIR / ".env"
    if not caminho.exists():
        return
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        os.environ.setdefault(chave.strip(), valor.strip().strip('"').strip("'"))


def seeds(repeticoes, base=SEED_BASE):
    """Devolve uma seed fixa por repetição, para amostras reproduzíveis."""
    return list(range(base, base + repeticoes))
