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


