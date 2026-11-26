import os
import re

BASE = os.path.dirname(os.path.abspath(__file__))
PASTA = os.path.join(BASE, "knowledge_b1")
TITULO = re.compile(
    r"^#\s+(\d+)\s+discos de ([ABC]) para ([ABC]) \(auxiliar ([ABC])\)\s*$"
)
MOVIMENTO = re.compile(r"^([ABC])->([ABC])$")


def hanoi(n, origem, destino, auxiliar):
    out = []

    def rec(n, o, d, a):
        if n == 0:
            return
        rec(n - 1, o, a, d)
        out.append((o, d))
        rec(n - 1, a, d, o)

    rec(n, origem, destino, auxiliar)
    return out


def subsequencia(seq, alvo):
    n = len(alvo)
    if n == 0:
        return False
    return any(seq[i:i + n] == alvo for i in range(len(seq) - n + 1))


def simular(seq, n, origem, destino):
    pinos = {"A": list(range(n, 0, -1)), "B": [], "C": []}
    if origem != "A":
        pinos["A"] = []
        pinos[origem] = list(range(n, 0, -1))
    for indice, (o, d) in enumerate(seq, 1):
        if not pinos[o]:
            return False, f"mov {indice}: pino {o} vazio"
        disco = pinos[o][-1]
        if pinos[d] and pinos[d][-1] < disco:
            return False, f"mov {indice}: disco {disco} sobre {pinos[d][-1]}"
        pinos[o].pop()
        pinos[d].append(disco)
    return pinos[destino] == list(range(n, 0, -1)), "ok"


alvo3 = hanoi(3, "A", "C", "B")
alvo4 = hanoi(4, "A", "C", "B")
print("alvo 3D A->C:", " ".join(f"{o}->{d}" for o, d in alvo3))
print("alvo 4D A->C:", " ".join(f"{o}->{d}" for o, d in alvo4))
print()
print(f"{'documento':<28} {'n':>2} {'movs':>4} {'resolve_titulo':>14} {'3D_A->C':>7} {'4D_A->C':>7}")
com3 = []
com4 = []
titulo_3d_ac = []
arquivos_4d = []
for nome in sorted(os.listdir(PASTA)):
    if not nome.endswith(".md"):
        continue
    caminho = os.path.join(PASTA, nome)
    with open(caminho, encoding="utf-8") as f:
        linhas = f.read().splitlines()
    titulo = None
    for linha in linhas:
        achado = TITULO.match(linha.strip())
        if achado:
            titulo = achado
            break
    movs = []
    for linha in linhas:
        achado = MOVIMENTO.match(linha.strip())
        if achado:
            movs.append((achado.group(1), achado.group(2)))
    tem3 = subsequencia(movs, alvo3)
    tem4 = subsequencia(movs, alvo4)
    if tem3:
        com3.append(nome)
    if tem4:
        com4.append(nome)
    if titulo:
        n, origem, destino, auxiliar = (
            int(titulo.group(1)), titulo.group(2), titulo.group(3), titulo.group(4)
        )
        if n == 3 and origem == "A" and destino == "C":
            titulo_3d_ac.append(nome)
        if n == 4:
            arquivos_4d.append(nome)
        ok, motivo = simular(movs, n, origem, destino)
        print(
            f"{nome:<28} {n:>2} {len(movs):>4} {str(ok):>14} "
            f"{str(tem3):>7} {str(tem4):>7}  {motivo}"
        )
    else:
        print(
            f"{nome:<28} {'-':>2} {len(movs):>4} {'-':>14} "
            f"{str(tem3):>7} {str(tem4):>7}"
        )
print()
print("documentos com sequencia completa 3D A->C:", com3 or "nenhum")
print("documentos com sequencia completa 4D A->C:", com4 or "nenhum")
print("documentos com titulo 3D A->C:", titulo_3d_ac or "nenhum")
print("documentos de 4 discos:", arquivos_4d or "nenhum")
