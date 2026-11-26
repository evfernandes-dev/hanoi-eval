import argparse
import json
import os
import sys
import time
from collections import Counter

import requests

import hanoi_eval as h
import rag
from experimento_rag import (
    avaliar,
    estado_para_texto,
    modelo_disponivel,
    registrar_falha,
)

BASE = os.path.dirname(os.path.abspath(__file__))
PASTA = os.path.join(BASE, "knowledge_b1")
TOP_K_PRINCIPAL = rag.TOP_K_RAG
TOP_K_EXTRA = 10
ORIGEM = "A"
DESTINO = "C"
AUXILIAR = "B"


def terceiro(a, b):
    return ({"A", "B", "C"} - {a, b}).pop()


def doc_bloco(discos, origem, destino):
    return f"{discos}_discos_{origem}_para_{destino}.md"


def preparar_contexto(conn, nivel, discos):
    auxiliar = AUXILIAR
    sub_discos = discos - 1
    sub1 = (ORIGEM, auxiliar, DESTINO)
    sub2 = (auxiliar, DESTINO, ORIGEM)
    alvo1 = doc_bloco(sub_discos, *sub1[:2])
    alvo2 = doc_bloco(sub_discos, *sub2[:2])
    consulta = rag.pergunta_para_instancia(discos, ORIGEM, DESTINO, auxiliar)
    principais = rag.buscar(
        conn, consulta, h.MODELO_EMBEDDING, PASTA, TOP_K_PRINCIPAL
    )
    trechos = list(principais)
    origens = {t["id"]: "principal" for t in principais}
    extras = []

    if nivel == "B2":
        for nome, (o, d, a), alvo in (
            ("sub1", sub1, alvo1),
            ("sub2", sub2, alvo2),
        ):
            consulta_sub = rag.pergunta_para_bloco(sub_discos, o, d, a)
            candidatos = rag.buscar(
                conn, consulta_sub, h.MODELO_EMBEDDING, PASTA, TOP_K_EXTRA
            )
            rank = next(
                (
                    i
                    for i, t in enumerate(candidatos, start=1)
                    if t["documento"] == alvo
                ),
                None,
            )
            extras.append(
                {
                    "nome": nome,
                    "consulta": consulta_sub,
                    "alvo": alvo,
                    "rank": rank,
                    "encontrado": rank is not None,
                }
            )
            if rank is not None:
                escolhido = candidatos[rank - 1]
                if escolhido["id"] not in origens:
                    trechos.append(escolhido)
                    origens[escolhido["id"]] = nome

    contexto = rag.montar_contexto(trechos)
    documentos = {t["documento"] for t in trechos}
    blocos = {
        "sub1": alvo1,
        "sub2": alvo2,
        "sub1_recuperado": alvo1 in documentos,
        "sub2_recuperado": alvo2 in documentos,
    }
    blocos["ambos"] = blocos["sub1_recuperado"] and blocos["sub2_recuperado"]
    meta = {
        "nivel": nivel,
        "consulta_principal": consulta,
        "top_k_principal": TOP_K_PRINCIPAL,
        "top_k_extra": TOP_K_EXTRA if nivel == "B2" else None,
        "consultas_extras": extras,
        "blocos_necessarios": blocos,
        "composicao_recuperada": "composicao.md" in documentos,
        "procedimento_recuperado": any(
            "Procedimento" in t["texto"] for t in trechos
        ),
        "chunks": [
            {
                "id": t["id"],
                "documento": t["documento"],
                "score": round(t["score"], 4),
                "origem": origens.get(t["id"], "principal"),
            }
            for t in trechos
        ],
    }
    return contexto, json.dumps(meta, ensure_ascii=False), meta


def rodar_instancia(
    conn, nivel, discos, modelo, seeds, temperatura, contexto, chunks_rag, digest
):
    modo = f"sem_memoria_{nivel.lower()}"
    execucao_id = h.criar_execucao(
        conn, modelo, discos, len(seeds), modo, digest, h.VERSAO_PROMPT, nivel
    )
    h.DISCOS = discos
    h.USAR_MEMORIA = False
    h.USAR_RAG = True
    base_prompt = h.montar_prompt([], contexto)
    minimos = 2 ** discos - 1
    print(
        f"\n=== {nivel} | {discos} discos | execucao #{execucao_id} "
        f"| RAG=True ==="
    )
    for tentativa, seed in enumerate(seeds, start=1):
        inicio = time.time()
        try:
            texto = h.perguntar_ollama(
                modelo, base_prompt, temperatura=temperatura, seed=seed
            )
        except requests.exceptions.ConnectionError:
            tempo = time.time() - inicio
            registrar_falha(
                conn, execucao_id, modelo, tentativa, minimos,
                "erro_ollama", "ollama offline", tempo, base_prompt,
                chunks_rag, temperatura, seed,
            )
            print(f"  t{tentativa} seed {seed}: Ollama offline")
            conn.close()
            sys.exit(1)
        except requests.exceptions.ReadTimeout:
            tempo = time.time() - inicio
            registrar_falha(
                conn, execucao_id, modelo, tentativa, minimos,
                "timeout", "timeout", tempo, base_prompt,
                chunks_rag, temperatura, seed,
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
                base_prompt, chunks_rag, temperatura, seed,
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
                base_prompt, chunks_rag, temperatura, seed,
            )
            print(f"  t{tentativa} seed {seed}: falha no Ollama")
            continue
        tempo = time.time() - inicio

        av = avaliar(texto, discos)
        h.registrar_resultado(
            conn, execucao_id, modelo, tentativa, minimos,
            av["resolveu"], av["feitos"], av["erro"], tempo, av["status"],
            base_prompt, texto, av["estado_final"], None,
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
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(DISTINCT tentativa), COALESCE(SUM(resolveu), 0), "
        "COALESCE(SUM(status = 'ok'), 0), COUNT(DISTINCT resposta_bruta) "
        "FROM resultados WHERE execucao_id = %s",
        (execucao_id,),
    )
    total, tolerante, estrito, distintas = cur.fetchone()
    cur.execute(
        "SELECT tentativa, estado_final FROM resultados "
        "WHERE execucao_id = %s ORDER BY tentativa",
        (execucao_id,),
    )
    estados = {
        t: e for t, e in cur.fetchall() if e is not None
    }
    cur.execute(
        "SELECT chunks_rag FROM resultados WHERE execucao_id = %s LIMIT 1",
        (execucao_id,),
    )
    linha = cur.fetchone()
    meta = json.loads(linha[0]) if linha and linha[0] else None
    cur.close()
    contagem = Counter(estados.values())
    comum = contagem.most_common(1)[0] if contagem else None
    return {
        "total": int(total),
        "estrito": int(estrito),
        "tolerante": int(tolerante),
        "distintas": int(distintas),
        "comum": comum,
        "meta": meta,
    }


def localizar_execucao(conn, rag_versao, discos):
    cur = conn.cursor()
    cur.execute(
        "SELECT id FROM execucoes WHERE rag_versao = %s AND discos = %s "
        "ORDER BY id DESC LIMIT 1",
        (rag_versao, discos),
    )
    linha = cur.fetchone()
    cur.close()
    return linha[0] if linha else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--niveis", default="B1,B2")
    parser.add_argument("--instancias", default="3,4")
    parser.add_argument("--repeticoes", type=int, default=10)
    parser.add_argument("--seed-base", type=int, default=9000)
    parser.add_argument("--temperatura", type=float, default=0.5)
    parser.add_argument("--modelo", default="qwen2.5:3b")
    args = parser.parse_args()

    niveis = [n.strip() for n in args.niveis.split(",") if n.strip()]
    instancias = [int(n) for n in args.instancias.split(",") if n.strip()]
    if any(n not in ("B1", "B2") for n in niveis):
        print("ERRO: niveis validos: B1,B2")
        return 1
    if not modelo_disponivel(args.modelo):
        print(f"ERRO: modelo '{args.modelo}' nao instalado.")
        return 1

    h.carregar_env()
    conn = h.conectar()
    h.criar_tabela(conn)
    rag.criar_tabela(conn)
    if not rag.modelo_instalado(h.MODELO_EMBEDDING):
        print(f"ERRO: embedding '{h.MODELO_EMBEDDING}' nao instalado.")
        return 1
    rag.indexar(conn, PASTA, h.MODELO_EMBEDDING)

    digest = h.obter_digest_modelo(args.modelo)
    seeds = [args.seed_base + i for i in range(args.repeticoes)]
    print(
        f"Config: modelo={args.modelo} | temp={args.temperatura} | "
        f"seeds={seeds} | top_k_principal={TOP_K_PRINCIPAL} | "
        f"top_k_extra={TOP_K_EXTRA} | prompt={h.VERSAO_PROMPT}"
    )

    metas = {}
    for nivel in niveis:
        for discos in instancias:
            contexto, chunks_rag, meta = preparar_contexto(conn, nivel, discos)
            metas[(nivel, discos)] = meta
            print(
                f"\n{nivel} | {discos} discos | blocos: "
                f"sub1={meta['blocos_necessarios']['sub1_recuperado']} "
                f"sub2={meta['blocos_necessarios']['sub2_recuperado']} "
                f"ambos={meta['blocos_necessarios']['ambos']} "
                f"comp={meta['composicao_recuperada']} "
                f"proc={meta['procedimento_recuperado']}"
            )
            for extra in meta["consultas_extras"]:
                print(
                    f"  extra {extra['nome']}: alvo={extra['alvo']} "
                    f"rank={extra['rank']} encontrado={extra['encontrado']}"
                )
            rodar_instancia(
                conn, nivel, discos, args.modelo, seeds, args.temperatura,
                contexto, chunks_rag, digest,
            )

    print("\n=== TABELA COMPARATIVA (sem RAG e R1 reaproveitados) ===")
    print(
        f"{'nivel':<22} {'instancia':<9} {'estrito':>8} {'tolerante':>9} "
        f"{'distintas':>9} {'blocos':>7} estado_final_mais_comum"
    )
    for rotulo, rag_versao in (
        ("sem RAG", "none"),
        ("R1", "R1"),
        ("B1", "B1"),
        ("B2 (retriever decompõe)", "B2"),
    ):
        for discos in (3, 4):
            execucao_id = localizar_execucao(conn, rag_versao, discos)
            if execucao_id is None:
                print(f"{rotulo:<22} {discos} discos  (execucao nao encontrada)")
                continue
            resumo = resumo_execucao(conn, execucao_id)
            estado = "-"
            if resumo["comum"]:
                estado_json, quantidade = resumo["comum"]
                estado = (
                    f"{estado_para_texto(estado_json)} "
                    f"({quantidade}/{resumo['total']})"
                )
            blocos = "-"
            meta = resumo["meta"]
            if rag_versao in ("B1", "B2") and meta:
                blocos = "sim" if meta["blocos_necessarios"]["ambos"] else "nao"
            print(
                f"{rotulo:<22} {f'{discos} discos':<9} "
                f"{resumo['estrito']}/{resumo['total']:<5} "
                f"{resumo['tolerante']}/{resumo['total']:<5} "
                f"{resumo['distintas']:>9} {blocos:>7} {estado}"
            )

    print("\nDetalhe dos blocos B1/B2:")
    for (nivel, discos), meta in sorted(metas.items()):
        blocos = meta["blocos_necessarios"]
        print(
            f"  {nivel} {discos}D: sub1={blocos['sub1_recuperado']} "
            f"sub2={blocos['sub2_recuperado']} "
            f"comp={meta['composicao_recuperada']} "
            f"proc={meta['procedimento_recuperado']}"
        )
        for extra in meta["consultas_extras"]:
            print(
                f"    {extra['nome']} rank={extra['rank']} "
                f"alvo={extra['alvo']} consulta={extra['consulta']!r}"
            )

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
