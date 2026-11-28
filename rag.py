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


def similaridade_cosseno(a, b):
    """Similaridade de cosseno entre dois vetores."""
    if not a or not b or len(a) != len(b):
        return 0.0
    produto = math.fsum(x * y for x, y in zip(a, b))
    norma_a = math.sqrt(math.fsum(x * x for x in a))
    norma_b = math.sqrt(math.fsum(y * y for y in b))
    if norma_a == 0 or norma_b == 0:
        return 0.0
    return produto / (norma_a * norma_b)


def ranquear(consulta_vetor, trechos, limite):
    """Ordena os trechos pela similaridade e devolve os mais relevantes."""
    pontuados = []
    for trecho in trechos:
        vetor = json.loads(trecho["embedding"])
        pontuados.append(
            {
                **trecho,
                "score": similaridade_cosseno(consulta_vetor, vetor),
            }
        )
    pontuados.sort(key=lambda item: item["score"], reverse=True)
    return pontuados[:limite]


def buscar(conn, pergunta, modelo_embedding, pasta, limite=3):
    """Gera o embedding da pergunta e busca os trechos mais parecidos."""
    documentos = carregar_documentos(pasta)
    hashes_atuais = {(doc["documento"], doc["hash"]) for doc in documentos}
    consulta_vetor = obter_embedding(pergunta, modelo_embedding)

    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT id, documento, hash_documento, texto, embedding
            FROM rag_trechos
            WHERE modelo_embedding = %s
            """,
            (modelo_embedding,),
        )
        linhas = [
            {
                "id": id_trecho,
                "documento": documento,
                "texto": texto,
                "embedding": embedding,
            }
            for id_trecho, documento, hash_documento, texto, embedding in cursor.fetchall()
            if (documento, hash_documento) in hashes_atuais
        ]
    finally:
        cursor.close()

    if not linhas:
        return []
    return ranquear(consulta_vetor, linhas, limite)


def montar_contexto(trechos):
    """Monta o texto que será colocado no prompt do modelo."""
    return "\n\n".join(
        f"[{numero}] {trecho['texto']}"
        for numero, trecho in enumerate(trechos, start=1)
    )


def versao_corpus(pasta):
    """Versão curta e reproduzível do corpus (cabe em VARCHAR(10))."""
    documentos = carregar_documentos(pasta)
    if not documentos:
        return "vazio"
    base = "\n".join(
        f"{doc['documento']}:{doc['hash']}" for doc in documentos
    )
    return "k" + hashlib.sha256(base.encode("utf-8")).hexdigest()[:8]


def pergunta_para_discos(discos, origem="A", destino="C", auxiliar="B"):
    return (
        f"mover {discos} discos da haste {origem} para a haste {destino} "
        f"usando {auxiliar} como auxiliar"
    )
