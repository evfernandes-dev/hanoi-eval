# rag.py
# Funcoes simples de RAG: documentos, embeddings, MySQL e busca por cosseno.

import hashlib
import json
import math
import os
import re

import requests

OLLAMA_EMBED_URL = "http://localhost:11434/api/embed"
OLLAMA_TAGS_URL = "http://localhost:11434/api/tags"
TIMEOUT_EMBEDDING = 120
MAX_CARACTERES_TRECHO = 700
VERSAO_DIVISAO = "v2"  # muda quando a forma de dividir os documentos mudar
TOP_K_RAG = 10


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


# Cria a tabela de trechos; nao altera as tabelas existentes.
def criar_tabela(conn):
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS rag_trechos (
            id INT AUTO_INCREMENT PRIMARY KEY,
            documento VARCHAR(255) NOT NULL,
            hash_documento CHAR(64) NOT NULL,
            modelo_embedding VARCHAR(100) NOT NULL,
            ordem INT NOT NULL,
            texto TEXT NOT NULL,
            embedding LONGTEXT NOT NULL,
            criado_em DATETIME NOT NULL
        )
        """
    )
    conn.commit()
    cursor.close()


# Indexa os documentos no MySQL; pula o que ja esta indexado.
def indexar(conn, pasta, modelo_embedding):
    documentos = carregar_documentos(pasta)
    for doc in documentos:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT COUNT(*) FROM rag_trechos
            WHERE documento = %s AND hash_documento = %s AND modelo_embedding = %s
            """,
            (doc["documento"], doc["hash"], modelo_embedding),
        )
        existentes = cursor.fetchone()[0]
        cursor.close()

        if existentes:
            print(f"RAG: {doc['documento']} ja indexado ({existentes} trechos).")
            continue

        print(f"RAG: indexando {doc['documento']} ({len(doc['trechos'])} trechos)...")
        vetores = [
            obter_embedding(trecho, modelo_embedding)
            for trecho in doc["trechos"]
        ]

        cursor = conn.cursor()
        for ordem, (trecho, vetor) in enumerate(zip(doc["trechos"], vetores), start=1):
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
        cursor.close()
        print(f"RAG: {doc['documento']} indexado.")


# Calcula a similaridade de cosseno entre dois vetores.
def similaridade_cosseno(a, b):
    if not a or not b or len(a) != len(b):
        return 0.0
    produto = math.fsum(x * y for x, y in zip(a, b))
    norma_a = math.sqrt(math.fsum(x * x for x in a))
    norma_b = math.sqrt(math.fsum(y * y for y in b))
    if norma_a == 0 or norma_b == 0:
        return 0.0
    return produto / (norma_a * norma_b)


# Ordena os trechos pela similaridade e devolve os mais relevantes.
def ranquear(consulta_vetor, trechos, limite):
    pontuados = []
    for trecho in trechos:
        vetor = json.loads(trecho["embedding"])
        score = similaridade_cosseno(consulta_vetor, vetor)
        pontuados.append({**trecho, "score": score})
    pontuados.sort(key=lambda item: item["score"], reverse=True)
    return pontuados[:limite]


# Gera o embedding da pergunta e busca os trechos mais parecidos.
def buscar(conn, pergunta, modelo_embedding, pasta, limite=3):
    documentos = carregar_documentos(pasta)
    hashes_atuais = {(d["documento"], d["hash"]) for d in documentos}
    consulta_vetor = obter_embedding(pergunta, modelo_embedding)

    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, documento, hash_documento, texto, embedding
        FROM rag_trechos
        WHERE modelo_embedding = %s
        """,
        (modelo_embedding,),
    )
    linhas = []
    for id_trecho, documento, hash_documento, texto, embedding in cursor.fetchall():
        if (documento, hash_documento) in hashes_atuais:
            linhas.append(
                {
                    "id": id_trecho,
                    "documento": documento,
                    "texto": texto,
                    "embedding": embedding,
                }
            )
    cursor.close()

    if not linhas:
        return []
    return ranquear(consulta_vetor, linhas, limite)


# Monta o texto que sera colocado no prompt do Qwen.
def montar_contexto(trechos):
    partes = []
    for numero, trecho in enumerate(trechos, start=1):
        partes.append(f"[{numero}] {trecho['texto']}")
    return "\n\n".join(partes)


# Pergunta fixa usada para recuperar conhecimentos sobre o problema.
def pergunta_para_discos(discos):
    return pergunta_para_instancia(discos, "A", "C", "B")


# Consulta concreta com número de discos e papéis das hastes.
def pergunta_para_instancia(discos, origem, destino, auxiliar):
    return (
        f"mover {discos} discos da haste {origem} para a haste {destino} "
        f"usando {auxiliar} como auxiliar"
    )


# Consulta específica pelo título do bloco resolvido.
def pergunta_para_bloco(discos, origem, destino, auxiliar):
    return f"{discos} discos de {origem} para {destino} (auxiliar {auxiliar})"
