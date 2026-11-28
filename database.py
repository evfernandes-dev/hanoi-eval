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


