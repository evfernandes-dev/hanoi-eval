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
