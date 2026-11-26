import argparse
import json
import os
import re
import sys
import time
from collections import Counter

import requests

import hanoi_eval as h
import rag

BASE = os.path.dirname(os.path.abspath(__file__))
TOP_K = rag.TOP_K_RAG
NIVEIS = {
    "sem_rag": {
        "rotulo": "sem RAG", "pasta": None, "rag_versao": "none",
        "modo": "sem_memoria_sem_rag",
    },
    "R1": {
        "rotulo": "R1", "pasta": "knowledge", "rag_versao": "R1",
        "modo": "sem_memoria_r1",
    },
    "R2": {
        "rotulo": "R2", "pasta": "knowledge_r2", "rag_versao": "R2",
        "modo": "sem_memoria_r2",
    },
    "R3": {
        "rotulo": "R3", "pasta": "knowledge_r3", "rag_versao": "R3",
        "modo": "sem_memoria_r3",
    },
    "R4": {
        "rotulo": "R4 (controle)", "pasta": "knowledge_r4", "rag_versao": "R4",
        "modo": "sem_memoria_r4",
    },
}

CADEIA = re.compile(
    r"^[ABC](?:\s*(?:-+>|=>|→|⇒)\s*[ABC])+[\s,;.]*$",
    re.IGNORECASE,
)
CADEIA_HINT = re.compile(
    r"[ABC]\s*(?:-+>|=>|→|⇒)\s*[ABC]\s*(?:-+>|=>|→|⇒)\s*[ABC]",
    re.IGNORECASE,
)


def modelo_disponivel(modelo):
    try:
        resposta = requests.get(h.OLLAMA_TAGS_URL, timeout=10)
        resposta.raise_for_status()
        nomes = [m.get("name", "") for m in resposta.json().get("models", [])]
    except (requests.exceptions.RequestException, ValueError):
        return False
    alvo = modelo.strip()
    if alvo in nomes:
        return True
    if ":" in alvo:
        return False
    return any(nome.split(":")[0] == alvo for nome in nomes)


def estado_para_texto(estado_json):
    dados = json.loads(estado_json)
    partes = []
    for pino in ("A", "B", "C"):
        discos = ",".join(str(d) for d in dados[pino])
        partes.append(f"{pino}=[{discos}]")
    return ", ".join(partes)


def _simular(movimentos, discos):
    if not movimentos:
        return (
            False, 0,
            "formato inválido (nenhum movimento A->C encontrado)",
            None, "vazio",
        )
    efetivos = [(o, d) for o, d in movimentos if o != d]
    pinos = {"A": list(range(discos, 0, -1)), "B": [], "C": []}
    erro = None
    motivo = "ok"
    for numero, (origem, destino) in enumerate(efetivos, start=1):
        if not pinos[origem]:
            erro = f"{numero} (pino {origem} vazio)"
            motivo = "ilegal"
            break
        disco = pinos[origem][-1]
        if pinos[destino] and pinos[destino][-1] < disco:
            erro = f"{numero} (disco {disco} sobre disco {pinos[destino][-1]})"
            motivo = "ilegal"
            break
        pinos[origem].pop()
        pinos[destino].append(disco)
    resolveu = erro is None and pinos["C"] == list(range(discos, 0, -1))
    if not resolveu and erro is None:
        erro = f"{len(efetivos) + 1} (torre incompleta)"
        motivo = "incompleta"
    estado = json.dumps(pinos, ensure_ascii=False)
    return resolveu, len(efetivos), erro, estado, motivo


def _extrair_tolerante(resposta):
    movimentos = []
    composto = False
    for linha in (resposta or "").splitlines():
        linha = h.MARCADOR_LINHA.sub("", linha).strip()
        linha = h.PREFIXO_PASSO.sub("", linha).strip()
        if not linha:
            continue
        if CADEIA_HINT.search(linha):
            composto = True
        if CADEIA.match(linha):
            nodes = re.findall(r"[ABC]", linha.upper())
            movimentos.extend(zip(nodes, nodes[1:]))
            continue
        achados = h.MOVIMENTO.findall(linha)
        if not achados:
            continue
        resto = h.MOVIMENTO.sub("", linha)
        if not h.RESIDUO_MOVIMENTOS.match(resto):
            continue
        movimentos.extend((o.upper(), d.upper()) for o, d in achados)
    return movimentos, composto


def avaliar(resposta, discos):
    estritos = h._extrair_movimentos(resposta)
    tolerantes, composto = _extrair_tolerante(resposta)
    estrito_ok, _, estrito_erro, _, estrito_motivo = _simular(estritos, discos)
    tolerante_ok, tolerante_feitos, tolerante_erro, estado, _ = _simular(
        tolerantes, discos
    )

    if estrito_ok:
        status = "ok"
    elif not estritos and not tolerantes:
        status = "formato_invalido"
    elif composto:
        status = "formato_composto"
    elif estrito_motivo == "ilegal":
        status = "lance_ilegal"
    else:
        status = "torre_incompleta"

    if estrito_ok:
        erro = None if tolerante_ok else h._texto_curto(
            f"estrito: ok; tolerante: {tolerante_erro}"
        )
    elif composto:
        erro = h._texto_curto(
            f"estrito: {estrito_erro or 'ok'}; tolerante: {tolerante_erro or 'ok'}"
        )
    else:
        erro = tolerante_erro

    return {
        "resolveu": tolerante_ok,
        "estrito": estrito_ok,
        "tolerante": tolerante_ok,
        "composto": composto,
        "status": status,
        "feitos": tolerante_feitos,
        "erro": erro,
        "estado_final": estado,
    }


def montar_chunks_rag(trechos, discos, consulta):
    itens = []
    for trecho in trechos:
        texto = trecho["texto"]
        itens.append(
            {
                "id": trecho.get("id"),
                "documento": trecho["documento"],
                "score": round(trecho["score"], 4),
                "procedimento": "Procedimento" in texto,
                "procedimento_instancia": (
                    f"Procedimento para mover {discos} discos" in texto
                ),
                "inicio": " ".join(texto.split())[:140],
            }
        )
    return {
        "consulta": consulta,
        "top_k": TOP_K,
        "procedimento_recuperado": any(i["procedimento"] for i in itens),
        "procedimento_instancia_recuperado": any(
            i["procedimento_instancia"] for i in itens
        ),
        "chunks": itens,
    }


def preparar_rag(conn, pasta, discos):
    consulta = rag.pergunta_para_instancia(discos, "A", "C", "B")
    trechos = rag.buscar(
        conn, consulta, h.MODELO_EMBEDDING, pasta, TOP_K
    )
    contexto = rag.montar_contexto(trechos)
    meta = montar_chunks_rag(trechos, discos, consulta)
    print(f"  RAG {discos} discos: consulta={consulta!r}")
    for item in meta["chunks"]:
        print(
            f"    [{item['id']}] {item['documento']} "
            f"score={item['score']:.4f} "
            f"proc={item['procedimento']} "
            f"proc_inst={item['procedimento_instancia']}"
        )
    if not meta["procedimento_instancia_recuperado"]:
        print("  AVISO: procedimento da instancia ausente do contexto.")
    elif not meta["procedimento_recuperado"]:
        print("  AVISO: nenhum chunk de procedimento recuperado.")
    return contexto, json.dumps(meta, ensure_ascii=False)


def registrar_falha(
    conn, execucao_id, modelo, tentativa, minimos, status, erro, tempo,
    prompt, chunks_rag, temperatura, seed,
):
    h.registrar_resultado(
        conn, execucao_id, modelo, tentativa, minimos,
        False, 0, h._texto_curto(erro), tempo, status,
        prompt, None, None, None,
        rodada=1, temperatura=temperatura, seed=seed,
        chunks_rag=chunks_rag,
    )


def rodar_instancia(
    conn, nivel, discos, modelo, seeds, temperatura, contexto, chunks_rag,
    digest,
):
    modo = nivel["modo"]
    execucao_id = h.criar_execucao(
        conn, modelo, discos, len(seeds), modo, digest, h.VERSAO_PROMPT,
        nivel["rag_versao"],
    )
    h.DISCOS = discos
    h.USAR_MEMORIA = False
    h.USAR_RAG = nivel["pasta"] is not None
    base_prompt = h.montar_prompt([], contexto)
    minimos = 2 ** discos - 1
    print(
        f"\n=== {nivel['rotulo']} | {discos} discos | execucao "
        f"#{execucao_id} | RAG={h.USAR_RAG} ==="
    )

    for tentativa, seed in enumerate(seeds, start=1):
        prompt = base_prompt
        inicio = time.time()
        try:
            texto = h.perguntar_ollama(
                modelo, prompt, temperatura=temperatura, seed=seed
            )
        except requests.exceptions.ConnectionError:
            tempo = time.time() - inicio
            registrar_falha(
                conn, execucao_id, modelo, tentativa, minimos,
                "erro_ollama", "ollama offline", tempo, prompt, chunks_rag,
                temperatura, seed,
            )
            print(f"  t{tentativa} seed {seed}: Ollama offline")
            conn.close()
            sys.exit(1)
        except requests.exceptions.ReadTimeout:
            tempo = time.time() - inicio
            registrar_falha(
                conn, execucao_id, modelo, tentativa, minimos,
                "timeout", "timeout", tempo, prompt, chunks_rag,
                temperatura, seed,
            )
            print(f"  t{tentativa} seed {seed}: timeout | {tempo:.2f}s")
            continue
        except requests.exceptions.HTTPError as e:
            tempo = time.time() - inicio
            codigo = e.response.status_code if e.response is not None else None
            status = "modelo_ausente" if codigo == 404 else "http_erro"
            registrar_falha(
                conn, execucao_id, modelo, tentativa, minimos,
                status, h._texto_curto(f"HTTP {codigo}: {e}"), tempo,
                prompt, chunks_rag, temperatura, seed,
            )
            print(f"  t{tentativa} seed {seed}: HTTP {codigo}")
            if codigo == 404:
                conn.close()
                sys.exit(1)
            continue
        except requests.exceptions.RequestException as e:
            tempo = time.time() - inicio
            registrar_falha(
                conn, execucao_id, modelo, tentativa, minimos,
                "erro_ollama", h._texto_curto(f"falha no Ollama: {e}"), tempo,
                prompt, chunks_rag, temperatura, seed,
            )
            print(f"  t{tentativa} seed {seed}: falha no Ollama")
            continue
        tempo = time.time() - inicio

        av = avaliar(texto, discos)
        h.registrar_resultado(
            conn, execucao_id, modelo, tentativa, minimos,
            av["resolveu"], av["feitos"], av["erro"], tempo, av["status"],
            prompt, texto, av["estado_final"], None,
            rodada=1, temperatura=temperatura, seed=seed,
            chunks_rag=chunks_rag,
        )
        print(
            f"  t{tentativa} seed {seed}: status={av['status']} | "
            f"estrito={av['estrito']} tolerante={av['tolerante']} | "
            f"{av['feitos']} movimentos | {tempo:.2f}s"
        )

    return execucao_id


def resumo_execucao(conn, execucao_id):
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT COUNT(DISTINCT tentativa), COALESCE(SUM(resolveu), 0),
               COALESCE(SUM(status = 'ok'), 0),
               COUNT(DISTINCT resposta_bruta)
        FROM resultados WHERE execucao_id = %s
        """,
        (execucao_id,),
    )
    total, tolerante, estrito, distintas = cursor.fetchone()
    cursor.execute(
        "SELECT tentativa, estado_final FROM resultados "
        "WHERE execucao_id = %s ORDER BY tentativa",
        (execucao_id,),
    )
    estados = {
        tentativa: estado
        for tentativa, estado in cursor.fetchall()
        if estado is not None
    }
    cursor.execute(
        "SELECT chunks_rag FROM resultados WHERE execucao_id = %s LIMIT 1",
        (execucao_id,),
    )
    linha = cursor.fetchone()
    chunks_rag = json.loads(linha[0]) if linha and linha[0] else None
    cursor.close()

    contagem = Counter(estados.values())
    estado_comum = contagem.most_common(1)[0] if contagem else None
    return {
        "total": int(total),
        "estrito": int(estrito),
        "tolerante": int(tolerante),
        "distintas": int(distintas),
        "estado_comum": estado_comum,
        "chunks_rag": chunks_rag,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--niveis", default="sem_rag,R1,R2,R3,R4",
        help="lista separada por virgula",
    )
    parser.add_argument("--instancias", default="3,4")
    parser.add_argument("--repeticoes", type=int, default=10)
    parser.add_argument("--seed-base", type=int, default=9000)
    parser.add_argument("--temperatura", type=float, default=0.5)
    parser.add_argument("--modelo", default="qwen2.5:3b")
    args = parser.parse_args()

    niveis = [n.strip() for n in args.niveis.split(",") if n.strip()]
    instancias = [int(n) for n in args.instancias.split(",") if n.strip()]
    if any(n not in NIVEIS for n in niveis):
        print(f"ERRO: niveis invalidos: {niveis}")
        return 1
    if not modelo_disponivel(args.modelo):
        print(f"ERRO: modelo '{args.modelo}' nao esta instalado.")
        return 1

    h.carregar_env()
    conn = h.conectar()
    h.criar_tabela(conn)
    rag.criar_tabela(conn)
    if not rag.modelo_instalado(h.MODELO_EMBEDDING):
        print(f"ERRO: embedding '{h.MODELO_EMBEDDING}' nao instalado.")
        return 1

    digest = h.obter_digest_modelo(args.modelo)
    seeds = [args.seed_base + i for i in range(args.repeticoes)]
    print(
        f"Config: modelo={args.modelo} | temperatura={args.temperatura} | "
        f"seeds={seeds} | top_k={TOP_K} | prompt={h.VERSAO_PROMPT} | "
        f"digest={digest}"
    )

    resultados = []
    for nome_nivel in niveis:
        nivel = NIVEIS[nome_nivel]
        pasta = (
            os.path.join(BASE, nivel["pasta"]) if nivel["pasta"] else None
        )
        if pasta:
            print(f"\n### Indexando nivel {nivel['rotulo']} em {pasta}")
            rag.indexar(conn, pasta, h.MODELO_EMBEDDING)
        for discos in instancias:
            if pasta:
                contexto, chunks_rag = preparar_rag(conn, pasta, discos)
            else:
                contexto, chunks_rag = "", None
            execucao_id = rodar_instancia(
                conn, nivel, discos, args.modelo, seeds, args.temperatura,
                contexto, chunks_rag, digest,
            )
            resumo = resumo_execucao(conn, execucao_id)
            resumo.update(
                {
                    "nivel": nivel["rotulo"],
                    "rag_versao": nivel["rag_versao"],
                    "instancia": f"{discos} discos",
                    "execucao_id": execucao_id,
                }
            )
            resultados.append(resumo)

    print("\n=== TABELA FINAL ===")
    cabecalho = (
        f"{'nivel':<14} {'instancia':<9} {'estrito':>8} {'tolerante':>9} "
        f"{'distintas':>9} {'procedimento':>13} estado_final_mais_comum"
    )
    print(cabecalho)
    for resumo in resultados:
        estado = "-"
        if resumo["estado_comum"]:
            estado_json, quantidade = resumo["estado_comum"]
            estado = (
                f"{estado_para_texto(estado_json)} "
                f"({quantidade}/{resumo['total']})"
            )
        meta = resumo["chunks_rag"]
        if meta is None:
            proc = "-"
        elif meta.get("procedimento_instancia_recuperado"):
            proc = f"sim ({resumo['total']}/{resumo['total']})"
        elif meta.get("procedimento_recuperado"):
            proc = "so geral"
        else:
            proc = "nao"
        print(
            f"{resumo['nivel']:<14} {resumo['instancia']:<9} "
            f"{resumo['estrito']}/{resumo['total']:<5} "
            f"{resumo['tolerante']}/{resumo['total']:<5} "
            f"{resumo['distintas']:>9} {proc:>13} {estado}"
        )

    ausentes = [
        r for r in resultados
        if r["chunks_rag"] is not None
        and not r["chunks_rag"].get("procedimento_instancia_recuperado")
    ]
    if ausentes:
        print("\nAVISO: procedimento da instancia ausente em:")
        for r in ausentes:
            print(
                f"  {r['nivel']} | {r['instancia']} | execucao "
                f"#{r['execucao_id']}"
            )
    else:
        print(
            "\nVerificacao: procedimento da instancia recuperado em "
            "todas as execucoes RAG."
        )

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
