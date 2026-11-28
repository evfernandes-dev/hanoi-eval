"""Conexão com MySQL e persistência das execuções."""

import json
import os

import mysql.connector

from config import carregar_env


def conectar():
    """Abre a conexão usando apenas variáveis de ambiente."""
    carregar_env()
    return mysql.connector.connect(
        host=os.environ.get("MYSQL_HOST", "localhost"),
        user=os.environ.get("MYSQL_USER", "root"),
        password=os.environ.get("MYSQL_PASSWORD", ""),
        database=os.environ.get("MYSQL_DATABASE", "hanoi"),
        charset="utf8mb4",
    )


def _coluna_existe(conn, tabela, coluna):
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT COUNT(*) FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = %s AND COLUMN_NAME = %s
            """,
            (tabela, coluna),
        )
        return cursor.fetchone()[0] > 0
    finally:
        cursor.close()


def criar_tabelas(conn):
    """Cria as tabelas e aplica apenas migrações aditivas."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS execucoes (
                id INT AUTO_INCREMENT PRIMARY KEY,
                data DATETIME NOT NULL,
                modelo VARCHAR(100) NOT NULL,
                discos INT NOT NULL,
                repeticoes INT NOT NULL,
                modo VARCHAR(30) NOT NULL,
                modelo_digest VARCHAR(64) NULL,
                prompt_versao VARCHAR(10) NOT NULL DEFAULT 'v1',
                rag_versao VARCHAR(10) NULL
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS resultados (
                id INT AUTO_INCREMENT PRIMARY KEY,
                execucao_id INT NULL,
                data DATETIME NOT NULL,
                modelo VARCHAR(100) NOT NULL,
                discos INT NOT NULL,
                tentativa INT NOT NULL,
                resolveu BOOLEAN NOT NULL,
                movimentos_feitos INT NOT NULL,
                movimentos_minimos INT NOT NULL,
                erro_no_movimento VARCHAR(255) NULL,
                tempo_segundos FLOAT NOT NULL,
                usou_memoria BOOLEAN NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'ok',
                prompt MEDIUMTEXT NULL,
                resposta_bruta MEDIUMTEXT NULL,
                estado_final TEXT NULL,
                rodada INT NOT NULL DEFAULT 1,
                temperatura FLOAT NULL,
                seed INT NULL,
                usou_rag BOOLEAN NOT NULL DEFAULT 0,
                chunks TEXT NULL,
                chunks_rag TEXT NULL
            )
            """
        )
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
    finally:
        cursor.close()

    migracoes = {
        ("resultados", "execucao_id"): "INT NULL",
        ("resultados", "status"): "VARCHAR(20) NOT NULL DEFAULT 'ok'",
        ("resultados", "prompt"): "MEDIUMTEXT NULL",
        ("resultados", "resposta_bruta"): "MEDIUMTEXT NULL",
        ("resultados", "estado_final"): "TEXT NULL",
        ("resultados", "rodada"): "INT NOT NULL DEFAULT 1",
        ("resultados", "temperatura"): "FLOAT NULL",
        ("resultados", "seed"): "INT NULL",
        ("resultados", "usou_rag"): "BOOLEAN NOT NULL DEFAULT 0",
        ("resultados", "chunks"): "TEXT NULL",
        ("resultados", "chunks_rag"): "TEXT NULL",
        ("execucoes", "modelo_digest"): "VARCHAR(64) NULL",
        ("execucoes", "prompt_versao"): "VARCHAR(10) NOT NULL DEFAULT 'v1'",
        ("execucoes", "rag_versao"): "VARCHAR(10) NULL",
    }
    for (tabela, coluna), definicao in migracoes.items():
        if not _coluna_existe(conn, tabela, coluna):
            cursor = conn.cursor()
            try:
                cursor.execute(
                    f"ALTER TABLE {tabela} ADD COLUMN {coluna} {definicao}"
                )
                conn.commit()
            finally:
                cursor.close()


def criar_execucao(
    conn,
    *,
    modelo,
    discos,
    repeticoes,
    modo,
    modelo_digest,
    prompt_versao,
    rag_versao=None,
):
    """Cria uma execução e devolve o id gerado."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO execucoes
                (data, modelo, discos, repeticoes, modo, modelo_digest,
                 prompt_versao, rag_versao)
            VALUES (NOW(), %(modelo)s, %(discos)s, %(repeticoes)s, %(modo)s,
                    %(modelo_digest)s, %(prompt_versao)s, %(rag_versao)s)
            """,
            {
                "modelo": modelo,
                "discos": discos,
                "repeticoes": repeticoes,
                "modo": modo,
                "modelo_digest": modelo_digest,
                "prompt_versao": prompt_versao,
                "rag_versao": rag_versao,
            },
        )
        execucao_id = cursor.lastrowid
        conn.commit()
        return execucao_id
    finally:
        cursor.close()


def _json(valor):
    """Serializa dicts/listas; strings e None passam como estão."""
    if valor is None or isinstance(valor, str):
        return valor
    return json.dumps(valor, ensure_ascii=False)


def _texto_curto(texto, limite=255):
    if texto is None:
        return None
    return " ".join(str(texto).split())[:limite]


def registrar_resultado(
    conn,
    *,
    execucao_id,
    modelo,
    discos,
    tentativa,
    rodada,
    resolveu,
    movimentos_feitos,
    movimentos_minimos,
    erro,
    tempo_segundos,
    status,
    prompt,
    resposta_bruta,
    estado_final,
    chunks=None,
    temperatura=None,
    seed=None,
    usou_rag=False,
    usou_memoria=False,
):
    """Grava uma chamada ao modelo, inclusive quando ela falha."""
    parametros = {
        "execucao_id": execucao_id,
        "modelo": modelo,
        "discos": discos,
        "tentativa": tentativa,
        "rodada": rodada,
        "resolveu": int(bool(resolveu)),
        "movimentos_feitos": movimentos_feitos,
        "movimentos_minimos": movimentos_minimos,
        "erro_no_movimento": _texto_curto(erro),
        "tempo_segundos": round(float(tempo_segundos), 2),
        "status": status,
        "prompt": prompt,
        "resposta_bruta": resposta_bruta,
        "estado_final": _json(estado_final),
        "chunks": _json(chunks),
        "temperatura": temperatura,
        "seed": seed,
        "usou_rag": int(bool(usou_rag)),
        "usou_memoria": int(bool(usou_memoria)),
    }
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO resultados
                (data, execucao_id, modelo, discos, tentativa, resolveu,
                 movimentos_feitos, movimentos_minimos, erro_no_movimento,
                 tempo_segundos, usou_memoria, status, prompt, resposta_bruta,
                 estado_final, rodada, temperatura, seed, usou_rag, chunks)
            VALUES (NOW(), %(execucao_id)s, %(modelo)s, %(discos)s,
                    %(tentativa)s, %(resolveu)s, %(movimentos_feitos)s,
                    %(movimentos_minimos)s, %(erro_no_movimento)s,
                    %(tempo_segundos)s, %(usou_memoria)s, %(status)s,
                    %(prompt)s, %(resposta_bruta)s, %(estado_final)s,
                    %(rodada)s, %(temperatura)s, %(seed)s, %(usou_rag)s,
                    %(chunks)s)
            """,
            parametros,
        )
        conn.commit()
    finally:
        cursor.close()
