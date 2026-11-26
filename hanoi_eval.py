# hanoi_eval.py
# Testa modelos locais do Ollama resolvendo a Torre de Hanói,
# grava cada tentativa no MySQL e usa uma memoria de erros nos prompts.

import json
import os
import re
import sys
import time

import mysql.connector
import requests

import rag

# ===== Configuracoes =====
MODELOS = ["qwen2.5:3b"]
DISCOS = 3
REPETICOES = 10
USAR_MEMORIA = False
USAR_RAG = True
VERSAO_PROMPT = "v2"
MODELO_EMBEDDING = "nomic-embed-text"
TOP_K = 3
PASTA_CONHECIMENTO = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "knowledge"
)

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_TAGS_URL = "http://localhost:11434/api/tags"
TIMEOUT = 180
MOVIMENTO = re.compile(r"([ABC])\s*(?:-+>|=>|→|⇒)\s*([ABC])", re.IGNORECASE)
MARCADOR_LINHA = re.compile(r"^\s*(?:(?:[-*•–—]|\d+[.)])\s*)+")
PREFIXO_PASSO = re.compile(
    r"^(?:passo|movimento|jogada|move|step)\s*\d*\s*[:.\-–—)]\s*",
    re.IGNORECASE,
)
RESIDUO_MOVIMENTOS = re.compile(
    r"^[\s,;.()\[\]|•–—\-]*(?:(?:e|and)[\s,;.()\[\]|•–—\-]*)*$",
    re.IGNORECASE,
)


# Le o .env sem biblioteca extra; nao sobrescreve variaveis ja definidas no sistema.
def carregar_env():
    caminho = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(caminho):
        return
    with open(caminho, "r", encoding="utf-8") as arquivo:
        for linha in arquivo:
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            chave, valor = linha.split("=", 1)
            os.environ.setdefault(chave.strip(), valor.strip().strip('"').strip("'"))


# Abre a conexao com o MySQL usando apenas variaveis de ambiente.
def conectar():
    try:
        return mysql.connector.connect(
            host=os.environ.get("MYSQL_HOST", "localhost"),
            user=os.environ.get("MYSQL_USER", "root"),
            password=os.environ.get("MYSQL_PASSWORD", ""),
            database=os.environ.get("MYSQL_DATABASE", "hanoi"),
        )
    except mysql.connector.Error as e:
        print(f"ERRO: nao foi possivel conectar ao MySQL: {e}")
        print("Confira as variaveis do .env e se o MySQL esta rodando (veja o README).")
        sys.exit(1)


# Verifica se uma coluna existe na tabela do banco atual.
def coluna_existe(conn, tabela, coluna):
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT COUNT(*) FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s AND COLUMN_NAME = %s
        """,
        (tabela, coluna),
    )
    existe = cursor.fetchone()[0] > 0
    cursor.close()
    return existe


# Cria as tabelas necessarias e migra bancos antigos sem apagar dados.
def criar_tabela(conn):
    cursor = conn.cursor()
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
    conn.commit()
    cursor.close()

    # Migracao aditiva: apenas adiciona a coluna; registros antigos ficam com o default.
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
        if not coluna_existe(conn, tabela, coluna):
            cursor = conn.cursor()
            cursor.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {definicao}")
            conn.commit()
            cursor.close()


# Cria uma execucao e devolve o id gerado para associar aos resultados.
def criar_execucao(
    conn, modelo, discos, repeticoes, modo, modelo_digest, prompt_versao,
    rag_versao=None,
):
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO execucoes
            (data, modelo, discos, repeticoes, modo, modelo_digest,
             prompt_versao, rag_versao)
        VALUES (NOW(), %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            modelo, discos, repeticoes, modo, modelo_digest, prompt_versao,
            rag_versao,
        ),
    )
    execucao_id = cursor.lastrowid
    conn.commit()
    cursor.close()
    return execucao_id


# Grava uma tentativa, inclusive quando o Ollama falha ou a resposta e invalida.
def registrar_resultado(
    conn,
    execucao_id,
    modelo,
    tentativa,
    minimos,
    resolveu,
    feitos,
    erro,
    tempo,
    status,
    prompt,
    resposta_bruta,
    estado_final,
    chunks,
    rodada=1,
    temperatura=None,
    seed=None,
    chunks_rag=None,
):
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO resultados
            (data, execucao_id, modelo, discos, tentativa, resolveu,
             movimentos_feitos, movimentos_minimos, erro_no_movimento,
             tempo_segundos, usou_memoria, status, prompt, resposta_bruta,
             estado_final, rodada, temperatura, seed, usou_rag, chunks,
             chunks_rag)
        VALUES (NOW(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            execucao_id,
            modelo,
            DISCOS,
            tentativa,
            resolveu,
            feitos,
            minimos,
            erro,
            round(tempo, 2),
            USAR_MEMORIA,
            status,
            prompt,
            resposta_bruta,
            estado_final,
            rodada,
            temperatura,
            seed,
            USAR_RAG,
            chunks,
            chunks_rag,
        ),
    )
    conn.commit()
    cursor.close()


# Busca os ultimos erros
def buscar_erros(conn, modelo, discos):
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT erro_no_movimento FROM resultados
        WHERE modelo = %s AND discos = %s AND resolveu = 0
          AND erro_no_movimento IS NOT NULL
        ORDER BY id DESC
        LIMIT 10
        """,
        (modelo, discos),
    )
    erros = []
    for (erro,) in cursor.fetchall():
        if erro and erro not in erros:  # evita repetir o mesmo erro no prompt
            erros.append(erro)
    cursor.close()
    return erros


# Extrai movimentos de linhas com numeracao, bullets ou prefixo "Passo N:".
def _extrair_movimentos(resposta):
    movimentos = []
    for linha in (resposta or "").splitlines():
        linha = MARCADOR_LINHA.sub("", linha).strip()
        linha = PREFIXO_PASSO.sub("", linha).strip()
        if not linha:
            continue
        achados = MOVIMENTO.findall(linha)
        if not achados:
            continue
        resto = MOVIMENTO.sub("", linha)
        if not RESIDUO_MOVIMENTOS.match(resto):
            continue
        for origem, destino in achados:
            movimentos.append((origem.upper(), destino.upper()))
    return movimentos


# Simula os movimentos em 3 pinos
def validar(resposta, discos):
    movimentos = _extrair_movimentos(resposta)
    if not movimentos:
        return (
            False,
            0,
            "formato inválido (nenhum movimento A->C encontrado)",
            "formato_invalido",
            None,
        )

    # Movimentos para o mesmo pino nao alteram o estado e nao contam.
    efetivos = [(origem, destino) for origem, destino in movimentos
                if origem != destino]
    pinos = {"A": list(range(discos, 0, -1)), "B": [], "C": []}  # topo = ultimo item
    erro = None
    status = "ok"

    for numero, (origem, destino) in enumerate(efetivos, start=1):
        if not pinos[origem]:
            erro = f"{numero} (pino {origem} vazio)"
            status = "lance_ilegal"
            break
        disco = pinos[origem][-1]
        if pinos[destino] and pinos[destino][-1] < disco:
            erro = f"{numero} (disco {disco} sobre disco {pinos[destino][-1]})"
            status = "lance_ilegal"
            break
        pinos[origem].pop()
        pinos[destino].append(disco)

    resolveu = erro is None and pinos["C"] == list(range(discos, 0, -1))
    if not resolveu and erro is None:
        erro = f"{len(efetivos) + 1} (torre incompleta)"
        status = "torre_incompleta"

    estado_final = json.dumps(pinos, ensure_ascii=False)
    return resolveu, len(efetivos), erro, status, estado_final


# Monta o prompt. A base e identica nos tres modos; so contexto e memoria variam.
def montar_prompt(erros, contexto_rag=None):
    prompt = (
        f"Resolva a Torre de Hanói com {DISCOS} discos. Os pinos são A, B e C, "
        "todos os discos começam em A e devem terminar em C."
    )
    if USAR_RAG and contexto_rag:
        prompt += (
            "\n\nConhecimentos recuperados sobre a Torre de Hanói:\n"
            + contexto_rag
        )
    prompt += (
        "\n\nPlaneje internamente a escolha da haste auxiliar, mantenha a haste "
        "de destino livre para o maior disco e confira a validade de cada "
        "movimento. Não escreva o planejamento. Responda só com os movimentos, "
        "um por linha, no formato A->C. Sem explicações."
    )
    if USAR_MEMORIA and erros:
        prompt += (
            "\nNas tentativas anteriores você errou nos movimentos: "
            + ", ".join(erros)
            + ". Confira cada movimento com cuidado para não repetir esses erros."
        )
    return prompt


# Envia o prompt ao Ollama
def perguntar_ollama(modelo, prompt, temperatura=0, seed=None):
    opcoes = {"temperature": temperatura}
    if seed is not None:
        opcoes["seed"] = seed
    resposta = requests.post(
        OLLAMA_URL,
        json={
            "model": modelo,
            "prompt": prompt,
            "stream": False,
            "options": opcoes,
        },
        timeout=TIMEOUT,
    )
    resposta.raise_for_status()
    return resposta.json().get("response", "")


# Busca o digest exato do modelo no Ollama para registrar a versao usada.
def obter_digest_modelo(modelo):
    try:
        resposta = requests.get(OLLAMA_TAGS_URL, timeout=10)
        resposta.raise_for_status()
        modelos = resposta.json().get("models", [])
    except (requests.exceptions.RequestException, ValueError):
        return None

    alvo = modelo.strip()
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


# Limita textos de erro ao tamanho da coluna erro_no_movimento.
def _texto_curto(texto, limite=255):
    return " ".join(str(texto).split())[:limite]


def main():
    carregar_env()
    conn = conectar()
    criar_tabela(conn)
    minimos = 2 ** DISCOS - 1
    modo = "memoria" if USAR_MEMORIA else "sem_memoria"
    if USAR_RAG:
        modo += "_rag"

    contexto_rag = ""
    trechos = []
    chunks_info = None
    if USAR_RAG:
        print(f"RAG: ativado | modelo de embedding: {MODELO_EMBEDDING}")
        try:
            if not rag.modelo_instalado(MODELO_EMBEDDING):
                print(
                    f"ERRO: modelo de embedding '{MODELO_EMBEDDING}' nao instalado."
                )
                print(f"Rode: ollama pull {MODELO_EMBEDDING}")
                conn.close()
                sys.exit(1)

            rag.criar_tabela(conn)
            rag.indexar(conn, PASTA_CONHECIMENTO, MODELO_EMBEDDING)
            pergunta = rag.pergunta_para_discos(DISCOS)
            trechos = rag.buscar(
                conn, pergunta, MODELO_EMBEDDING, PASTA_CONHECIMENTO, TOP_K
            )
            contexto_rag = rag.montar_contexto(trechos)
            chunks_info = json.dumps(
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
            documentos = sorted({t["documento"] for t in trechos})
            print(
                f"RAG: {len(trechos)} trechos recuperados | documentos: "
                f"{', '.join(documentos) if documentos else 'nenhum'}"
            )
            for numero, trecho in enumerate(trechos, start=1):
                print(
                    f"  [{numero}] {trecho['documento']} | "
                    f"similaridade={trecho['score']:.4f}"
                )
                print("      " + trecho["texto"].replace("\n", "\n      "))
            if not trechos:
                print("RAG: nenhum trecho encontrado; seguindo sem contexto.")
        except requests.exceptions.ConnectionError:
            print("ERRO: o Ollama nao esta rodando em http://localhost:11434.")
            conn.close()
            sys.exit(1)
        except requests.exceptions.RequestException as e:
            print(f"ERRO ao gerar embeddings no Ollama: {e}")
            conn.close()
            sys.exit(1)
        except mysql.connector.Error as e:
            print(f"ERRO no MySQL ao preparar o RAG: {e}")
            conn.close()
            sys.exit(1)
        except (RuntimeError, ValueError) as e:
            print(f"ERRO no RAG: {e}")
            conn.close()
            sys.exit(1)
    else:
        print("RAG: desativado")

    print(
        f"Modelos: {len(MODELOS)} | discos: {DISCOS} | repeticoes: {REPETICOES} "
        f"| memoria: {USAR_MEMORIA} | rag: {USAR_RAG} | prompt: {VERSAO_PROMPT} "
        f"| minimo de movimentos: {minimos}\n"
    )

    for modelo in MODELOS:
        digest = obter_digest_modelo(modelo)
        execucao_id = criar_execucao(
            conn, modelo, DISCOS, REPETICOES, modo, digest, VERSAO_PROMPT
        )
        print(
            f"=== {modelo} | execucao #{execucao_id} | modo: {modo} "
            f"| prompt: {VERSAO_PROMPT} ==="
        )
        tempos = []
        movimentos_ok = []
        acertos = 0
        tentativas_registradas = 0

        # Repete o teste para cada modelo.
        for tentativa in range(1, REPETICOES + 1):
            erros = buscar_erros(conn, modelo, DISCOS) if USAR_MEMORIA else []
            prompt = montar_prompt(erros, contexto_rag)

            inicio = time.time()
            try:
                texto = perguntar_ollama(modelo, prompt)
            except requests.exceptions.ConnectionError:
                tempo = time.time() - inicio
                registrar_resultado(
                    conn, execucao_id, modelo, tentativa, minimos,
                    False, 0, "ollama offline", tempo, "erro_ollama",
                    prompt, None, None, chunks_info,
                )
                print(
                    f"tentativa {tentativa}/{REPETICOES}: status: erro_ollama "
                    f"(Ollama offline) | {tempo:.2f}s"
                )
                print("ERRO: o Ollama nao esta rodando em http://localhost:11434.")
                print("Inicie com 'ollama serve' e rode o script de novo.")
                conn.close()
                sys.exit(1)
            except requests.exceptions.ReadTimeout:
                tempo = time.time() - inicio
                registrar_resultado(
                    conn, execucao_id, modelo, tentativa, minimos,
                    False, 0, "timeout", tempo, "timeout",
                    prompt, None, None, chunks_info,
                )
                tentativas_registradas += 1
                print(
                    f"tentativa {tentativa}/{REPETICOES}: status: timeout | "
                    f"{tempo:.2f}s"
                )
                continue
            except requests.exceptions.HTTPError as e:
                tempo = time.time() - inicio
                codigo = e.response.status_code if e.response is not None else None
                if codigo == 404:
                    registrar_resultado(
                        conn, execucao_id, modelo, tentativa, minimos,
                        False, 0, "HTTP 404 (modelo ausente)", tempo,
                        "modelo_ausente", prompt, None, chunks_info,
                    )
                    tentativas_registradas += 1
                    print(
                        f"ERRO: modelo '{modelo}' nao encontrado. "
                        f"Rode: ollama pull {modelo}"
                    )
                    break
                registrar_resultado(
                    conn, execucao_id, modelo, tentativa, minimos,
                    False, 0, _texto_curto(f"HTTP {codigo}: {e}"), tempo,
                    "http_erro", prompt, None, chunks_info,
                )
                tentativas_registradas += 1
                print(
                    f"tentativa {tentativa}/{REPETICOES}: status: http_erro "
                    f"({e}) | {tempo:.2f}s"
                )
                continue
            except requests.exceptions.RequestException as e:
                tempo = time.time() - inicio
                registrar_resultado(
                    conn, execucao_id, modelo, tentativa, minimos,
                    False, 0, _texto_curto(f"falha no Ollama: {e}"), tempo,
                    "erro_ollama", prompt, None, chunks_info,
                )
                tentativas_registradas += 1
                print(
                    f"tentativa {tentativa}/{REPETICOES}: status: erro_ollama "
                    f"({e}) | {tempo:.2f}s"
                )
                continue
            tempo = time.time() - inicio

            resolveu, feitos, erro, status, estado_final = validar(texto, DISCOS)
            registrar_resultado(
                conn, execucao_id, modelo, tentativa, minimos,
                resolveu, feitos, erro, tempo, status,
                prompt, texto, estado_final, chunks_info,
            )

            tentativas_registradas += 1
            if status in ("ok", "lance_ilegal", "torre_incompleta"):
                tempos.append(tempo)
            if resolveu:
                acertos += 1
                movimentos_ok.append(feitos)

            if status == "ok":
                situacao = "OK"
            else:
                situacao = f"{status}: {erro}"
            print(
                f"tentativa {tentativa}/{REPETICOES}: {situacao} | "
                f"{feitos} movimentos | {tempo:.2f}s"
            )

        # Resumo simples do modelo.
        print()
        if tentativas_registradas == 0:
            print(f"Resumo {modelo}: nenhuma tentativa registrada.\n")
            continue

        taxa = acertos / tentativas_registradas * 100
        print(f"Acertos: {acertos} de {tentativas_registradas} = {taxa:.0f}%")
        if movimentos_ok:
            media = sum(movimentos_ok) / len(movimentos_ok)
            print(f"Media de movimentos (acertos): {media:.1f} | minimo: {minimos}")
        else:
            print("Media de movimentos (acertos): sem acertos")
        if tempos:
            print(
                f"Tempo medio (respostas validas): "
                f"{sum(tempos) / len(tempos):.2f}s\n"
            )
        else:
            print("Tempo medio (respostas validas): sem respostas validas\n")

    conn.close()


if __name__ == "__main__":
    main()
