# rag.py
# Le os documentos markdown, divide em trechos e gera embeddings.

import hashlib
import os
import re

import requests

OLLAMA_EMBED_URL = "http://localhost:11434/api/embed"
OLLAMA_TAGS_URL = "http://localhost:11434/api/tags"
TIMEOUT_EMBEDDING = 120
MAX_CARACTERES_TRECHO = 700
VERSAO_DIVISAO = "v2"  # muda quando a forma de dividir os documentos mudar


# Verifica se o modelo de embedding esta instalado, sem baixar nada.
def modelo_instalado(modelo_embedding):
    resposta = requests.get(OLLAMA_TAGS_URL, timeout=10)
    resposta.raise_for_status()
    modelos = [m.get("name", "") for m in resposta.json().get("models", [])]
    nome_base = modelo_embedding.split(":")[0]
    return any(nome.split(":")[0] == nome_base for nome in modelos)


# Calcula um hash que tambem identifica a versao da divisao em trechos.
def calcular_hash(texto):
    conteudo = f"{VERSAO_DIVISAO}\n{texto}"
    return hashlib.sha256(conteudo.encode("utf-8")).hexdigest()


# Le os arquivos .md da pasta e devolve nome, hash e trechos.
def carregar_documentos(pasta):
    documentos = []
    if not os.path.isdir(pasta):
        return documentos
    for nome in sorted(os.listdir(pasta)):
        if not nome.lower().endswith(".md"):
            continue
        caminho = os.path.join(pasta, nome)
        with open(caminho, "r", encoding="utf-8") as arquivo:
            texto = arquivo.read()
        documentos.append(
            {
                "documento": nome,
                "hash": calcular_hash(texto),
                "trechos": dividir_em_trechos(texto),
            }
        )
    return documentos


# Divide por secoes Markdown para nao separar titulo e conteudo.
def dividir_em_trechos(texto, max_caracteres=MAX_CARACTERES_TRECHO):
    secoes = re.split(r"(?m)(?=^#{1,6}\s+)", texto)
    trechos = []
    for secao in secoes:
        secao = secao.strip()
        if not secao:
            continue
        linhas = [linha for linha in secao.splitlines() if linha.strip()]
        if len(linhas) == 1 and linhas[0].lstrip().startswith("#"):
            continue  # ignora um titulo isolado, sem conteudo
        if len(secao) <= max_caracteres:
            trechos.append(secao)
        else:
            trechos.extend(_dividir_secao_longa(secao, max_caracteres))
    return trechos


# Divide apenas secoes maiores que o limite, juntando paragrafos por vez.
def _dividir_secao_longa(secao, max_caracteres):
    blocos = [b.strip() for b in re.split(r"\n\s*\n", secao) if b.strip()]
    trechos = []
    atual = ""

    for bloco in blocos:
        if len(bloco) > max_caracteres:
            if atual:
                trechos.append(atual)
                atual = ""
            for inicio in range(0, len(bloco), max_caracteres):
                trechos.append(bloco[inicio:inicio + max_caracteres])
            continue
        if atual and len(atual) + len(bloco) + 2 > max_caracteres:
            trechos.append(atual)
            atual = bloco
        else:
            atual = (atual + "\n\n" + bloco).strip()

    if atual:
        trechos.append(atual)
    return trechos


# Gera o embedding de um texto usando o endpoint /api/embed do Ollama.
def obter_embedding(texto, modelo_embedding):
    resposta = requests.post(
        OLLAMA_EMBED_URL,
        json={"model": modelo_embedding, "input": texto},
        timeout=TIMEOUT_EMBEDDING,
    )
    resposta.raise_for_status()
    embeddings = resposta.json().get("embeddings") or []
    if not embeddings:
        raise RuntimeError("O Ollama nao retornou embeddings.")
    return embeddings[0]
