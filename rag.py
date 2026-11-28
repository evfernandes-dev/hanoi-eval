"""RAG simples: documentos markdown, embeddings do Ollama e busca por cosseno."""

import hashlib
import json
import math
import os
import re

import requests

import config

VERSAO_DIVISAO = "v2"
MAX_CARACTERES_TRECHO = 700


def calcular_hash(texto):
    """Hash que identifica o conteúdo e a versão da divisão em trechos."""
    conteudo = f"{VERSAO_DIVISAO}\n{texto}"
    return hashlib.sha256(conteudo.encode("utf-8")).hexdigest()


def carregar_documentos(pasta):
    """Lê os arquivos .md da pasta e devolve nome, hash e trechos."""
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


def dividir_em_trechos(texto, max_caracteres=MAX_CARACTERES_TRECHO):
    """Divide por seções Markdown para não separar título e conteúdo."""
    secoes = re.split(r"(?m)(?=^#{1,6}\s+)", texto)
    trechos = []
    for secao in secoes:
        secao = secao.strip()
        if not secao:
            continue
        linhas = [linha for linha in secao.splitlines() if linha.strip()]
        if len(linhas) == 1 and linhas[0].lstrip().startswith("#"):
            continue
        if len(secao) <= max_caracteres:
            trechos.append(secao)
        else:
            trechos.extend(_dividir_secao_longa(secao, max_caracteres))
    return trechos


def _dividir_secao_longa(secao, max_caracteres):
    blocos = [bloco.strip() for bloco in re.split(r"\n\s*\n", secao) if bloco.strip()]
    trechos = []
    atual = ""
    for bloco in blocos:
        if len(bloco) > max_caracteres:
            if atual:
                trechos.append(atual)
                atual = ""
            for inicio in range(0, len(bloco), max_caracteres):
                trechos.append(bloco[inicio : inicio + max_caracteres])
            continue
        if atual and len(atual) + len(bloco) + 2 > max_caracteres:
            trechos.append(atual)
            atual = bloco
        else:
            atual = (atual + "\n\n" + bloco).strip()
    if atual:
        trechos.append(atual)
    return trechos


def obter_embedding(texto, modelo_embedding):
    """Gera o embedding de um texto usando o endpoint /api/embed do Ollama."""
    resposta = requests.post(
        config.OLLAMA_EMBED_URL,
        json={"model": modelo_embedding, "input": texto},
        timeout=config.TIMEOUT_EMBEDDING,
    )
    resposta.raise_for_status()
    embeddings = resposta.json().get("embeddings") or []
    if not embeddings:
        raise RuntimeError("O Ollama não retornou embeddings.")
    return embeddings[0]


def modelo_instalado(modelo):
    """Verifica se um modelo está instalado, sem baixar nada."""
    resposta = requests.get(config.OLLAMA_TAGS_URL, timeout=10)
    resposta.raise_for_status()
    nomes = [item.get("name", "") for item in resposta.json().get("models", [])]
    alvo = modelo.strip()
    if alvo in nomes:
        return True
    if ":" in alvo:
        return False
    return any(nome.split(":")[0] == alvo for nome in nomes)


def indexar(conn, pasta, modelo_embedding):
    """Indexa no MySQL apenas os documentos ainda não indexados."""
    for doc in carregar_documentos(pasta):
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT COUNT(*) FROM rag_trechos
                WHERE documento = %s AND hash_documento = %s
                  AND modelo_embedding = %s
                """,
                (doc["documento"], doc["hash"], modelo_embedding),
            )
            existentes = cursor.fetchone()[0]
        finally:
            cursor.close()

        if existentes:
            print(f"RAG: {doc['documento']} já indexado ({existentes} trechos).")
            continue

        print(f"RAG: indexando {doc['documento']} ({len(doc['trechos'])} trechos)...")
        vetores = [
            obter_embedding(trecho, modelo_embedding) for trecho in doc["trechos"]
        ]

        cursor = conn.cursor()
        try:
            for ordem, (trecho, vetor) in enumerate(
                zip(doc["trechos"], vetores), start=1
            ):
                cursor.execute(
                    """
                    INSERT INTO rag_trechos
                        (documento, hash_documento, modelo_embedding, ordem,
                         texto, embedding, criado_em)
                    VALUES (%s, %s, %s, %s, %s, %s, NOW())
                    """,
                    (
                        doc["documento"],
                        doc["hash"],
                        modelo_embedding,
                        ordem,
                        trecho,
                        json.dumps(vetor),
                    ),
                )
            conn.commit()
        finally:
            cursor.close()
        print(f"RAG: {doc['documento']} indexado.")


