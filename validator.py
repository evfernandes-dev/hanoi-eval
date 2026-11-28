"""Validação determinística dos movimentos da Torre de Hanói.

O validador não confia no modelo: ele extrai os movimentos do texto,
simula cada jogada em três pinos e só considera vitória quando a torre
inteira está na haste C, na ordem correta.
"""

import json
import re
from dataclasses import dataclass

MOVIMENTO = re.compile(r"([ABC])\s*(?:-+>|=>|→|⇒)\s*([ABC])", re.IGNORECASE)
MARCADOR_LINHA = re.compile(r"^\s*(?:(?:[-*•–—]|\d+[.)])\s*)+")
PREFIXO_PASSO = re.compile(
    r"^(?:passo|movimento|jogada|move|step)\s*\d*\s*[:.\-–—)]\s*",
    re.IGNORECASE,
)
ANOTACAO_LINHA = re.compile(
    r"\b(?:passos?|movimentos?|jogadas?|moves?|steps?|discos?|disks?"
    r"|n[úu]meros?|nums?|n[ºo°])\b\s*(?:n[ºo°])?\s*[.:#]?\s*\d*",
    re.IGNORECASE,
)
RESIDUO_MOVIMENTOS = re.compile(
    r"^[\s,;.:()\[\]{}|•–—\-*_`0-9º°#]*"
    r"(?:(?:e|and|de|do|da|no|na|em|para)"
    r"[\s,;.:()\[\]{}|•–—\-*_`0-9º°#]*)*$",
    re.IGNORECASE,
)
PINOS = ("A", "B", "C")


@dataclass(frozen=True)
class Aplicacao:
    estado: dict[str, list[int]]
    movimentos: list[tuple[str, str]]
    erro: str | None
    status: str


@dataclass(frozen=True)
class Resultado:
    resolveu: bool
    movimentos: int
    erro: str | None
    status: str
    estado: dict[str, list[int]]
    estado_final: str


def estado_inicial(discos):
    """Estado inicial: todos os discos em A, do maior para o menor."""
    return {"A": list(range(discos, 0, -1)), "B": [], "C": []}


def copiar_estado(estado):
    """Copia os pinos para não alterar o estado recebido."""
    return {pino: list(estado[pino]) for pino in PINOS}


def estado_para_texto(estado):
    """Representa o estado da base para o topo: A=[4,3,2,1]."""
    return " ".join(
        f"{pino}=[{','.join(str(disco) for disco in estado[pino])}]"
        for pino in PINOS
    )


def movimentos_da_linha(linha):
    """Extrai movimentos de uma linha, aceitando numeração e anotações."""
    linha = MARCADOR_LINHA.sub("", linha or "").strip()
    linha = PREFIXO_PASSO.sub("", linha).strip()
    if not linha:
        return []
    achados = MOVIMENTO.findall(linha)
    if not achados:
        return []
    resto = ANOTACAO_LINHA.sub("", MOVIMENTO.sub("", linha))
    if not RESIDUO_MOVIMENTOS.match(resto):
        return []
    return [(origem.upper(), destino.upper()) for origem, destino in achados]


def extrair_movimentos(resposta):
    """Extrai movimentos de todas as linhas, mantendo a ordem do texto."""
    movimentos = []
    for linha in (resposta or "").splitlines():
        movimentos.extend(movimentos_da_linha(linha))
    return movimentos


