"""Execução dos experimentos da Torre de Hanói.

Estratégias:
- baseline: uma chamada ao modelo, sem contexto externo.
- rag: uma chamada com trechos recuperados de knowledge/.
- blocos: uma chamada por bloco, com o estado atualizado entre elas.
"""

import argparse
import json
import sys
import time
from dataclasses import dataclass

import mysql.connector
import requests

import config
import database
import rag
import validator


class OllamaErro(Exception):
    """Falha de comunicação com o Ollama."""

    def __init__(self, mensagem, status, fatal=False):
        super().__init__(mensagem)
        self.status = status
        self.fatal = fatal


@dataclass
class Tentativa:
    sucesso: bool
    valida: bool
    tempo: float
    movimentos: int
    etapas_ok: int = 0


def chamar_ollama(prompt, *, temperatura, seed):
    """Envia o prompt ao Ollama e traduz falhas para OllamaErro."""
    try:
        resposta = requests.post(
            config.OLLAMA_URL,
            json={
                "model": config.MODELO,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": temperatura, "seed": seed},
            },
            timeout=config.TIMEOUT_GERACAO,
        )
        resposta.raise_for_status()
    except requests.exceptions.ConnectionError as erro:
        raise OllamaErro(
            "O Ollama não está rodando em http://localhost:11434",
            "erro_ollama",
            fatal=True,
        ) from erro
    except requests.exceptions.ReadTimeout as erro:
        raise OllamaErro("timeout na geração", "timeout") from erro
    except requests.exceptions.HTTPError as erro:
        codigo = erro.response.status_code if erro.response is not None else None
        if codigo == 404:
            raise OllamaErro(
                f"modelo '{config.MODELO}' não encontrado",
                "modelo_ausente",
                fatal=True,
            ) from erro
        raise OllamaErro(f"HTTP {codigo}: {erro}", "http_erro") from erro
    except requests.exceptions.RequestException as erro:
        raise OllamaErro(
            f"falha na comunicação com o Ollama: {erro}", "erro_ollama"
        ) from erro

    try:
        return resposta.json().get("response", "")
    except ValueError as erro:
        raise OllamaErro("O Ollama retornou JSON inválido", "erro_ollama") from erro


