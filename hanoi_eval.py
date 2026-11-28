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


def obter_digest_modelo():
    """Busca o digest exato do modelo para registrar a versão usada."""
    try:
        resposta = requests.get(config.OLLAMA_TAGS_URL, timeout=10)
        resposta.raise_for_status()
        modelos = resposta.json().get("models", [])
    except (requests.exceptions.RequestException, ValueError):
        return None

    alvo = config.MODELO.strip()
    for item in modelos:
        if alvo in (item.get("name"), item.get("model")):
            return item.get("digest")
    if ":" in alvo:
        return None
    for item in modelos:
        nome = item.get("name") or item.get("model") or ""
        if nome.split(":")[0] == alvo:
            return item.get("digest")
    return None


def verificar_modelos(usar_rag):
    """Confere se o Ollama está acessível e se os modelos existem."""
    try:
        if not rag.modelo_instalado(config.MODELO):
            print(
                f"ERRO: modelo '{config.MODELO}' não instalado. "
                f"Rode: ollama pull {config.MODELO}"
            )
            return False
        if usar_rag and not rag.modelo_instalado(config.MODELO_EMBEDDING):
            print(
                f"ERRO: modelo de embedding '{config.MODELO_EMBEDDING}' "
                f"não instalado. Rode: ollama pull {config.MODELO_EMBEDDING}"
            )
            return False
    except requests.exceptions.RequestException:
        print("ERRO: o Ollama não está rodando em http://localhost:11434.")
        return False
    return True


def montar_prompt_base(discos):
    return (
        f"Resolva a Torre de Hanói com {discos} discos. Os pinos são A, B e C, "
        "todos os discos começam em A e devem terminar em C.\n\n"
        "Planeje internamente a escolha da haste auxiliar, mantenha a haste de "
        "destino livre para o maior disco e confira a validade de cada movimento. "
        "Não escreva o planejamento. Responda só com os movimentos, um por linha, "
        "no formato A->C. Sem explicações."
    )


def montar_prompt_rag(discos, contexto):
    return (
        "Conhecimentos recuperados sobre a Torre de Hanói:\n"
        f"{contexto}\n\n" + montar_prompt_base(discos)
    )


def montar_prompt_bloco(
    discos,
    estado,
    etapa,
    total,
    k,
    origem,
    destino,
    auxiliar,
    feitos_etapa,
):
    minimo_etapa = 2**k - 1
    rotulo = "disco" if k == 1 else "discos"
    return (
        f"Você está resolvendo a Torre de Hanói com {discos} discos.\n"
        "Estado atual (listas da base para o topo): "
        f"{validator.estado_para_texto(estado)}.\n\n"
        f"Etapa {etapa} de {total}: mover {k} {rotulo} da haste {origem} para a "
        f"haste {destino} usando {auxiliar} como auxiliar.\n"
        f"Movimentos já feitos nesta etapa: {feitos_etapa} de no mínimo "
        f"{minimo_etapa}.\n\n"
        "Escolha o próximo movimento válido. Responda só com um movimento no "
        "formato A->C. Sem explicações."
    )


def decompor(discos, origem="A", destino="C", auxiliar="B"):
    """Decompõe o problema nos três blocos clássicos."""
    if discos == 1:
        return [
            {
                "k": 1,
                "origem": origem,
                "destino": destino,
                "auxiliar": auxiliar,
            }
        ]
    sub = discos - 1
    return [
        {"k": sub, "origem": origem, "destino": auxiliar, "auxiliar": destino},
        {"k": 1, "origem": origem, "destino": destino, "auxiliar": auxiliar},
        {"k": sub, "origem": auxiliar, "destino": destino, "auxiliar": origem},
    ]


def plano(k, origem, destino, auxiliar):
    """Plano determinístico mínimo de k discos entre duas hastes."""
    if k == 0:
        return []
    return (
        plano(k - 1, origem, auxiliar, destino)
        + [(origem, destino)]
        + plano(k - 1, auxiliar, destino, origem)
    )


def registrar_falha(
    conn,
    execucao_id,
    discos,
    tentativa,
    rodada,
    erro,
    tempo,
    status,
    prompt,
    chunks,
    seed,
    estado_final=None,
):
    database.registrar_resultado(
        conn,
        execucao_id=execucao_id,
        modelo=config.MODELO,
        discos=discos,
        tentativa=tentativa,
        rodada=rodada,
        resolveu=False,
        movimentos_feitos=0,
        movimentos_minimos=2**discos - 1,
        erro=erro,
        tempo_segundos=tempo,
        status=status,
        prompt=prompt,
        resposta_bruta=None,
        estado_final=estado_final,
        chunks=chunks,
        temperatura=config.TEMPERATURA,
        seed=seed,
        usou_rag=bool(chunks),
    )


def executar_tentativa_simples(
    conn, execucao_id, discos, tentativa, prompt, seed, chunks
):
    inicio = time.perf_counter()
    try:
        texto = chamar_ollama(
            prompt, temperatura=config.TEMPERATURA, seed=seed
        )
    except OllamaErro as erro:
        tempo = time.perf_counter() - inicio
        registrar_falha(
            conn,
            execucao_id,
            discos,
            tentativa,
            1,
            str(erro),
            tempo,
            erro.status,
            prompt,
            chunks,
            seed,
        )
        print(f"  tentativa {tentativa}: {erro.status} ({erro}) | {tempo:.2f}s")
        if erro.fatal:
            raise
        return Tentativa(False, False, tempo, 0)

    tempo = time.perf_counter() - inicio
    resultado = validator.validar_torre(texto, discos)
    database.registrar_resultado(
        conn,
        execucao_id=execucao_id,
        modelo=config.MODELO,
        discos=discos,
        tentativa=tentativa,
        rodada=1,
        resolveu=resultado.resolveu,
        movimentos_feitos=resultado.movimentos,
        movimentos_minimos=2**discos - 1,
        erro=resultado.erro,
        tempo_segundos=tempo,
        status=resultado.status,
        prompt=prompt,
        resposta_bruta=texto,
        estado_final=resultado.estado_final,
        chunks=chunks,
        temperatura=config.TEMPERATURA,
        seed=seed,
        usou_rag=bool(chunks),
    )
    situacao = (
        "OK"
        if resultado.status == "ok"
        else f"{resultado.status}: {resultado.erro}"
    )
    print(
        f"  tentativa {tentativa}: {situacao} | "
        f"{resultado.movimentos} movimentos | {tempo:.2f}s"
    )
    return Tentativa(
        resultado.resolveu, True, tempo, resultado.movimentos
    )


def executar_tentativa_blocos(conn, execucao_id, discos, tentativa, seed):
    estado = validator.estado_inicial(discos)
    blocos = decompor(discos)
    tempo_total = 0.0
    movimentos_total = 0
    etapas_ok = 0

    for etapa, bloco in enumerate(blocos, start=1):
        plano_bloco = plano(
            bloco["k"],
            bloco["origem"],
            bloco["destino"],
            bloco["auxiliar"],
        )
        esperado = validator.aplicar(estado, plano_bloco)
        maximo_chamadas = len(plano_bloco) + 2
        feitos_etapa = 0
        chamadas_etapa = 0
        prompt = ""

        while chamadas_etapa < maximo_chamadas and estado != esperado:
            prompt = montar_prompt_bloco(
                discos,
                estado,
                etapa,
                len(blocos),
                bloco["k"],
                bloco["origem"],
                bloco["destino"],
                bloco["auxiliar"],
                feitos_etapa,
            )

            inicio = time.perf_counter()
            try:
                texto = chamar_ollama(
                    prompt, temperatura=config.TEMPERATURA, seed=seed
                )
            except OllamaErro as erro:
                tempo = time.perf_counter() - inicio
                tempo_total += tempo
                registrar_falha(
                    conn,
                    execucao_id,
                    discos,
                    tentativa,
                    etapa,
                    str(erro),
                    tempo,
                    erro.status,
                    prompt,
                    None,
                    seed,
                    estado_final=json.dumps(estado, ensure_ascii=False),
                )
                print(
                    f"  tentativa {tentativa} etapa {etapa}: {erro.status} "
                    f"({erro}) | {tempo:.2f}s"
                )
                if erro.fatal:
                    raise
                return Tentativa(
                    False, False, tempo_total, movimentos_total, etapas_ok
                )

            tempo = time.perf_counter() - inicio
            tempo_total += tempo
            chamadas_etapa += 1
            aplicacao = validator.aplicar_sequencia(texto, estado)
            movimentos_total += len(aplicacao.movimentos)
            feitos_etapa += len(aplicacao.movimentos)
            resolveu = aplicacao.estado["C"] == list(
                range(discos, 0, -1)
            )

            database.registrar_resultado(
                conn,
                execucao_id=execucao_id,
                modelo=config.MODELO,
                discos=discos,
                tentativa=tentativa,
                rodada=etapa,
                resolveu=resolveu,
                movimentos_feitos=len(aplicacao.movimentos),
                movimentos_minimos=2**discos - 1,
                erro=aplicacao.erro,
                tempo_segundos=tempo,
                status=aplicacao.status,
                prompt=prompt,
                resposta_bruta=texto,
                estado_final=json.dumps(
                    aplicacao.estado, ensure_ascii=False
                ),
                chunks=None,
                temperatura=config.TEMPERATURA,
                seed=seed,
                usou_rag=False,
            )
            print(
                f"  tentativa {tentativa} etapa {etapa}/{len(blocos)} "
                f"chamada {chamadas_etapa}: {aplicacao.status} | "
                f"{len(aplicacao.movimentos)} movimentos | {tempo:.2f}s"
            )

            if aplicacao.status != "ok":
                return Tentativa(
                    False, True, tempo_total, movimentos_total, etapas_ok
                )
            estado = aplicacao.estado
            if estado == esperado:
                etapas_ok += 1
            if resolveu:
                return Tentativa(
                    True, True, tempo_total, movimentos_total, etapas_ok
                )

        if estado != esperado:
            erro = (
                "bloco não atingiu o estado esperado após "
                f"{chamadas_etapa} chamadas e {feitos_etapa} movimentos"
            )
            registrar_falha(
                conn,
                execucao_id,
                discos,
                tentativa,
                etapa,
                erro,
                0.0,
                "torre_incompleta",
                prompt,
                None,
                seed,
                estado_final=json.dumps(estado, ensure_ascii=False),
            )
            print(
                f"  tentativa {tentativa} etapa {etapa}: "
                f"torre_incompleta | {erro}"
            )
            return Tentativa(
                False, True, tempo_total, movimentos_total, etapas_ok
            )

        if estado["C"] == list(range(discos, 0, -1)):
            return Tentativa(
                True, True, tempo_total, movimentos_total, etapas_ok
            )

    return Tentativa(
        False, True, tempo_total, movimentos_total, etapas_ok
    )


def resumir(estrategia, discos, tentativas):
    validas = [tentativa for tentativa in tentativas if tentativa.valida]
    sucessos = [tentativa for tentativa in validas if tentativa.sucesso]
    total = len(validas)
    taxa = len(sucessos) / total * 100 if total else 0.0

    print("\n=== Resumo ===")
    print(
        f"Tentativas válidas: {total} | "
        f"falhas de infraestrutura: {len(tentativas) - total}"
    )
    print(f"Acertos: {len(sucessos)} de {total} = {taxa:.0f}%")
    if sucessos:
        media = sum(t.movimentos for t in sucessos) / len(sucessos)
        print(
            f"Média de movimentos nos acertos: {media:.1f} | "
            f"mínimo: {2**discos - 1}"
        )
    else:
        print("Média de movimentos nos acertos: sem acertos")
    if validas:
        tempo_medio = sum(t.tempo for t in validas) / len(validas)
        print(f"Tempo médio por tentativa válida: {tempo_medio:.2f}s")
    if estrategia == "blocos":
        print(
            f"Bloco 1 concluído: "
            f"{sum(1 for t in validas if t.etapas_ok >= 1)}/{total}"
        )
        print(
            f"Bloco 2 concluído: "
            f"{sum(1 for t in validas if t.etapas_ok >= 2)}/{total}"
        )
        print(
            f"Bloco 3 concluído: "
            f"{sum(1 for t in validas if t.etapas_ok >= 3)}/{total}"
        )


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Laboratório Torre de Hanói com LLM local."
    )
    parser.add_argument(
        "--estrategia",
        choices=("baseline", "rag", "blocos"),
        required=True,
    )
    parser.add_argument("--discos", type=int, default=config.DISCOS_PADRAO)
    parser.add_argument(
        "--repeticoes", type=int, default=config.REPETICOES_PADRAO
    )
    args = parser.parse_args(argv)

    if args.discos < 1 or args.repeticoes < 1:
        print("ERRO: discos e repetições devem ser maiores que zero.")
        return 1

    usar_rag = args.estrategia == "rag"
    if not verificar_modelos(usar_rag):
        return 1

    try:
        conn = database.conectar()
    except mysql.connector.Error as erro:
        print(f"ERRO: não foi possível conectar ao MySQL: {erro}")
        print("Confira o .env e se o MySQL está rodando.")
        return 1

    try:
        database.criar_tabelas(conn)
        digest = obter_digest_modelo()
        contexto = None
        chunks = None
        rag_versao = None

        if usar_rag:
            try:
                rag.indexar(
                    conn, config.PASTA_CONHECIMENTO, config.MODELO_EMBEDDING
                )
                trechos = rag.buscar(
                    conn,
                    rag.pergunta_para_discos(args.discos),
                    config.MODELO_EMBEDDING,
                    config.PASTA_CONHECIMENTO,
                    config.TOP_K,
                )
            except (requests.exceptions.RequestException, RuntimeError) as erro:
                print(f"ERRO ao preparar o RAG: {erro}")
                return 1
            if not trechos:
                print("ERRO: nenhum trecho recuperado. Verifique knowledge/.")
                return 1
            contexto = rag.montar_contexto(trechos)
            chunks = json.dumps(
                [
                    {
                        "id": trecho.get("id"),
                        "documento": trecho["documento"],
                        "score": round(trecho["score"], 4),
                    }
                    for trecho in trechos
                ],
                ensure_ascii=False,
            )
            rag_versao = rag.versao_corpus(config.PASTA_CONHECIMENTO)
            print(
                f"RAG: {len(trechos)} trechos | corpus {rag_versao} | "
                f"{len(contexto)} caracteres"
            )
            for trecho in trechos:
                print(
                    f"  [{trecho.get('id')}] {trecho['documento']} | "
                    f"score={trecho['score']:.4f}"
                )

        execucao_id = database.criar_execucao(
            conn,
            modelo=config.MODELO,
            discos=args.discos,
            repeticoes=args.repeticoes,
            modo=args.estrategia,
            modelo_digest=digest,
            prompt_versao=config.VERSAO_PROMPT,
            rag_versao=rag_versao,
        )
        print(
            f"=== execução #{execucao_id} | {config.MODELO} | "
            f"{args.discos} discos | estratégia {args.estrategia} | "
            f"prompt {config.VERSAO_PROMPT} ==="
        )

        prompt_simples = None
        if args.estrategia == "baseline":
            prompt_simples = montar_prompt_base(args.discos)
        elif usar_rag:
            prompt_simples = montar_prompt_rag(args.discos, contexto)

        tentativas = []
        for numero, seed in enumerate(
            config.seeds(args.repeticoes), start=1
        ):
            print(f"\ntentativa {numero}/{args.repeticoes} | seed {seed}")
            try:
                if args.estrategia == "blocos":
                    tentativa = executar_tentativa_blocos(
                        conn, execucao_id, args.discos, numero, seed
                    )
                else:
                    tentativa = executar_tentativa_simples(
                        conn,
                        execucao_id,
                        args.discos,
                        numero,
                        prompt_simples,
                        seed,
                        chunks,
                    )
            except OllamaErro as erro:
                print(f"\nERRO FATAL: {erro}")
                tentativas.append(Tentativa(False, False, 0.0, 0))
                break
            tentativas.append(tentativa)

        resumir(args.estrategia, args.discos, tentativas)
    except mysql.connector.Error as erro:
        print(f"\nERRO no MySQL: {erro}")
        return 1
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
