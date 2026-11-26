import argparse
import json
import sys
import time
from collections import Counter

import requests

import hanoi_eval as h
import rag

BRACOS = [
    {
        "slug": "controle",
        "versao": "v3a",
        "modo": "v3a_controle_rag",
        "max_rodadas": 2,
    },
    {
        "slug": "estado",
        "versao": "v3b",
        "modo": "v3b_estado_rag",
        "max_rodadas": 2,
    },
    {
        "slug": "loop",
        "versao": "v3c",
        "modo": "v3c_loop_rag",
        "max_rodadas": 3,
    },
]


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


def montar_feedback(versao, estado_json, discos):
    if estado_json is None:
        return (
            "Sua resposta não pôde ser interpretada. Responda apenas com "
            "movimentos no formato A->C, um por linha."
        )
    alvo = ",".join(str(d) for d in range(discos, 0, -1))
    estado = estado_para_texto(estado_json)
    if versao == "v3b":
        return (
            f"Sua tentativa terminou com {estado}; a torre precisa terminar "
            f"com C=[{alvo}]. Gere uma nova sequência completa."
        )
    return (
        f"Sua tentativa terminou com {estado}; a torre precisa terminar "
        f"com C=[{alvo}]. Corrija a sequência."
    )


def buscar_estado_anterior(conn, execucao_id, tentativa, rodada, modelo, discos, modo):
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT r.estado_final
        FROM resultados r
        JOIN execucoes e ON e.id = r.execucao_id
        WHERE r.execucao_id = %s AND r.tentativa = %s AND r.rodada = %s
          AND r.modelo = %s AND r.discos = %s AND e.modo = %s
        ORDER BY r.id DESC
        LIMIT 1
        """,
        (execucao_id, tentativa, rodada, modelo, discos, modo),
    )
    linha = cursor.fetchone()
    cursor.close()
    return linha[0] if linha else None


def preparar_rag(conn, discos):
    if not rag.modelo_instalado(h.MODELO_EMBEDDING):
        print(f"ERRO: modelo de embedding '{h.MODELO_EMBEDDING}' nao instalado.")
        sys.exit(1)
    rag.criar_tabela(conn)
    rag.indexar(conn, h.PASTA_CONHECIMENTO, h.MODELO_EMBEDDING)
    pergunta = rag.pergunta_para_discos(discos)
    trechos = rag.buscar(
        conn, pergunta, h.MODELO_EMBEDDING, h.PASTA_CONHECIMENTO, h.TOP_K
    )
    contexto = rag.montar_contexto(trechos)
    chunks_info = json.dumps(
        [
            {
                "id": t.get("id"),
                "documento": t["documento"],
                "score": round(t["score"], 4),
            }
            for t in trechos
        ],
        ensure_ascii=False,
    )
    print(f"RAG: {len(trechos)} trechos recuperados")
    for numero, trecho in enumerate(trechos, start=1):
        print(
            f"  [{numero}] {trecho['documento']} | "
            f"similaridade={trecho['score']:.4f}"
        )
    return contexto, chunks_info


def registrar_falha(
    conn, execucao_id, modelo, tentativa, minimos, status, erro, tempo,
    prompt, chunks, rodada, temperatura, seed,
):
    h.registrar_resultado(
        conn, execucao_id, modelo, tentativa, minimos,
        False, 0, h._texto_curto(erro), tempo, status,
        prompt, None, None, chunks,
        rodada=rodada, temperatura=temperatura, seed=seed,
    )


def executar_braco(
    conn, braco, discos, modelo, repeticoes, seeds, temperatura,
    base_prompt, chunks_info, digest,
):
    versao = braco["versao"]
    modo = braco["modo"]
    max_rodadas = braco["max_rodadas"]
    minimos = 2 ** discos - 1
    execucao_id = h.criar_execucao(
        conn, modelo, discos, repeticoes, modo, digest, versao
    )
    print(
        f"\n=== {versao} | execucao #{execucao_id} | modo {modo} "
        f"| max {max_rodadas} rodadas ==="
    )

    for indice, seed in enumerate(seeds, start=1):
        tentativa = indice
        acertou_na_rodada = None
        for rodada in range(1, max_rodadas + 1):
            prompt = base_prompt
            if rodada > 1:
                if versao == "v3a":
                    feedback = "Sua resposta estava errada. Tente novamente."
                else:
                    estado_anterior = buscar_estado_anterior(
                        conn, execucao_id, tentativa, rodada - 1,
                        modelo, discos, modo,
                    )
                    feedback = montar_feedback(versao, estado_anterior, discos)
                prompt = base_prompt + "\n\n" + feedback

            inicio = time.time()
            try:
                texto = h.perguntar_ollama(
                    modelo, prompt, temperatura=temperatura, seed=seed
                )
            except requests.exceptions.ConnectionError:
                tempo = time.time() - inicio
                registrar_falha(
                    conn, execucao_id, modelo, tentativa, minimos,
                    "erro_ollama", "ollama offline", tempo,
                    prompt, chunks_info, rodada, temperatura, seed,
                )
                print(f"[{versao} t{tentativa} r{rodada}] Ollama offline")
                conn.close()
                sys.exit(1)
            except requests.exceptions.ReadTimeout:
                tempo = time.time() - inicio
                registrar_falha(
                    conn, execucao_id, modelo, tentativa, minimos,
                    "timeout", "timeout", tempo,
                    prompt, chunks_info, rodada, temperatura, seed,
                )
                print(f"[{versao} t{tentativa} r{rodada}] timeout | {tempo:.2f}s")
                break
            except requests.exceptions.HTTPError as e:
                tempo = time.time() - inicio
                codigo = e.response.status_code if e.response is not None else None
                status = "modelo_ausente" if codigo == 404 else "http_erro"
                registrar_falha(
                    conn, execucao_id, modelo, tentativa, minimos,
                    status, h._texto_curto(f"HTTP {codigo}: {e}"), tempo,
                    prompt, chunks_info, rodada, temperatura, seed,
                )
                print(f"[{versao} t{tentativa} r{rodada}] HTTP {codigo}")
                if codigo == 404:
                    conn.close()
                    sys.exit(1)
                break
            except requests.exceptions.RequestException as e:
                tempo = time.time() - inicio
                registrar_falha(
                    conn, execucao_id, modelo, tentativa, minimos,
                    "erro_ollama", h._texto_curto(f"falha no Ollama: {e}"), tempo,
                    prompt, chunks_info, rodada, temperatura, seed,
                )
                print(f"[{versao} t{tentativa} r{rodada}] falha no Ollama")
                break
            tempo = time.time() - inicio

            resolveu, feitos, erro, status, estado_final = h.validar(texto, discos)
            h.registrar_resultado(
                conn, execucao_id, modelo, tentativa, minimos,
                resolveu, feitos, erro, tempo, status,
                prompt, texto, estado_final, chunks_info,
                rodada=rodada, temperatura=temperatura, seed=seed,
            )
            print(
                f"[{versao} t{tentativa} r{rodada} seed {seed}] "
                f"status={status} | {feitos} movimentos | {tempo:.2f}s"
            )
            if resolveu:
                acertou_na_rodada = rodada
                break

        if acertou_na_rodada is None:
            print(f"  tentativa {tentativa}/{repeticoes}: falhou")
        else:
            print(
                f"  tentativa {tentativa}/{repeticoes}: acertou na "
                f"rodada {acertou_na_rodada}"
            )

    return execucao_id


def resumo_execucao(conn, execucao_id):
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(DISTINCT tentativa), COALESCE(SUM(resolveu), 0) "
        "FROM resultados WHERE execucao_id = %s",
        (execucao_id,),
    )
    tentativas, acertos = cursor.fetchone()
    cursor.execute(
        "SELECT AVG(rodada) FROM resultados "
        "WHERE execucao_id = %s AND resolveu = 1",
        (execucao_id,),
    )
    rodada_media = cursor.fetchone()[0]
    cursor.execute(
        "SELECT COUNT(DISTINCT resposta_bruta) FROM resultados "
        "WHERE execucao_id = %s AND resposta_bruta IS NOT NULL",
        (execucao_id,),
    )
    distintas = cursor.fetchone()[0]
    cursor.execute(
        "SELECT COUNT(DISTINCT resposta_bruta) FROM resultados "
        "WHERE execucao_id = %s AND rodada = 1 AND resposta_bruta IS NOT NULL",
        (execucao_id,),
    )
    distintas_r1 = cursor.fetchone()[0]
    cursor.execute(
        "SELECT tentativa, estado_final FROM resultados "
        "WHERE execucao_id = %s ORDER BY tentativa, rodada",
        (execucao_id,),
    )
    ultimo_estado = {}
    for tentativa, estado in cursor.fetchall():
        if estado is not None:
            ultimo_estado[tentativa] = estado
    cursor.close()

    contagem = Counter(
        estado for estado in ultimo_estado.values() if estado is not None
    )
    estado_comum = contagem.most_common(1)[0] if contagem else None
    return {
        "tentativas": int(tentativas),
        "acertos": int(acertos),
        "rodada_media": float(rodada_media) if rodada_media is not None else None,
        "distintas": int(distintas),
        "distintas_r1": int(distintas_r1),
        "estado_comum": estado_comum,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--discos", type=int, default=3)
    parser.add_argument("--modelo", default="qwen2.5:3b")
    parser.add_argument("--repeticoes", type=int, default=10)
    parser.add_argument("--temperatura", type=float, default=0.5)
    parser.add_argument("--seed-base", type=int, default=7000)
    args = parser.parse_args()

    if args.discos < 1:
        print("ERRO: discos deve ser >= 1")
        return 1
    if args.repeticoes < 1:
        print("ERRO: repeticoes deve ser >= 1")
        return 1
    if not modelo_disponivel(args.modelo):
        print(f"ERRO: modelo '{args.modelo}' nao esta instalado no Ollama.")
        return 1

    h.carregar_env()
    h.DISCOS = args.discos
    h.USAR_MEMORIA = False
    h.USAR_RAG = True
    conn = h.conectar()
    h.criar_tabela(conn)

    contexto_rag, chunks_info = preparar_rag(conn, args.discos)
    base_prompt = h.montar_prompt([], contexto_rag)
    digest = h.obter_digest_modelo(args.modelo)
    seeds = [args.seed_base + i for i in range(args.repeticoes)]

    print(
        f"\nConfig: discos={args.discos} | modelo={args.modelo} "
        f"| repeticoes={args.repeticoes} | temperatura={args.temperatura} "
        f"| seeds={seeds} | digest={digest}"
    )
    print("Base prompt igual nos 3 bracos; so o feedback muda.")

    resultados = []
    for braco in BRACOS:
        execucao_id = executar_braco(
            conn, braco, args.discos, args.modelo, args.repeticoes, seeds,
            args.temperatura, base_prompt, chunks_info, digest,
        )
        resumo = resumo_execucao(conn, execucao_id)
        resumo["braco"] = braco["versao"]
        resumo["modo"] = braco["modo"]
        resumo["execucao_id"] = execucao_id
        resultados.append(resumo)

    print("\n=== TABELA FINAL ===")
    print(
        f"{'braco':<5} {'acertos':>8} {'rodada_media':>13} "
        f"{'distintas':>10} {'distintas_r1':>13} {'estado_final_mais_comum'}"
    )
    for resumo in resultados:
        media = (
            f"{resumo['rodada_media']:.2f}"
            if resumo["rodada_media"] is not None else "-"
        )
        estado = "-"
        if resumo["estado_comum"]:
            estado_json, quantidade = resumo["estado_comum"]
            estado = (
                f"{estado_para_texto(estado_json)} "
                f"({quantidade}/{resumo['tentativas']})"
            )
        print(
            f"{resumo['braco']:<5} "
            f"{resumo['acertos']}/{resumo['tentativas']:<6} "
            f"{media:>13} {resumo['distintas']:>10} "
            f"{resumo['distintas_r1']:>13} {estado}"
        )

    respostas_identicas = any(
        r["distintas_r1"] == 1 for r in resultados if r["tentativas"] > 1
    )
    if respostas_identicas:
        print(
            "\nAVISO: houve braco com todas as respostas da rodada 1 identicas; "
            "o n nao e independente."
        )
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
