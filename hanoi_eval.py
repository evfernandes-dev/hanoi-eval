# hanoi_eval.py
# Testa modelos locais do Ollama resolvendo a Torre de Hanói,
# grava cada tentativa no MySQL e usa uma memoria de erros nos prompts.

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
REPETICOES = 5
USAR_MEMORIA = False
USAR_RAG = True
MODELO_EMBEDDING = "nomic-embed-text"
TOP_K = 3
PASTA_CONHECIMENTO = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "knowledge"
)

OLLAMA_URL = "http://localhost:11434/api/generate"
TIMEOUT = 180
FORMATO_MOVIMENTO = re.compile(r"^\s*([ABC])\s*->\s*([ABC])\s*$", re.IGNORECASE)


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
            modo VARCHAR(30) NOT NULL
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
            usou_memoria BOOLEAN NOT NULL
        )
        """
    )
    conn.commit()
    cursor.close()

    # Migracao aditiva: apenas adiciona a coluna; registros antigos ficam NULL.
    if not coluna_existe(conn, "resultados", "execucao_id"):
        cursor = conn.cursor()
        cursor.execute("ALTER TABLE resultados ADD COLUMN execucao_id INT NULL")
        conn.commit()
        cursor.close()


# Cria uma execucao e devolve o id gerado para associar aos resultados.
def criar_execucao(conn, modelo, discos, repeticoes, modo):
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO execucoes (data, modelo, discos, repeticoes, modo)
        VALUES (NOW(), %s, %s, %s, %s)
        """,
        (modelo, discos, repeticoes, modo),
    )
    execucao_id = cursor.lastrowid
    conn.commit()
    cursor.close()
    return execucao_id


# Busca os erros!!!!
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


# Simula os movimentos em 3 pinos
def validar(resposta, discos):
    # Le apenas as linhas no formato A->C; o resto e ignorado.
    movimentos = []
    for linha in resposta.splitlines():
        achado = FORMATO_MOVIMENTO.match(linha)
        if achado:
            movimentos.append((achado.group(1).upper(), achado.group(2).upper()))

    pinos = {"A": list(range(discos, 0, -1)), "B": [], "C": []}  # topo = ultimo item
    erro = None

    for numero, (origem, destino) in enumerate(movimentos, start=1):
        if origem == destino:  # movimento sem efeito, nao conta como erro
            continue
        if not pinos[origem]:
            erro = f"{numero} (pino {origem} vazio)"
            break
        disco = pinos[origem][-1]
        if pinos[destino] and pinos[destino][-1] < disco:
            erro = f"{numero} (disco {disco} sobre disco {pinos[destino][-1]})"
            break
        pinos[origem].pop()
        pinos[destino].append(disco)

    resolveu = erro is None and pinos["C"] == list(range(discos, 0, -1))
    if not resolveu and erro is None:
        erro = f"{len(movimentos) + 1} (torre incompleta)"

    return resolveu, len(movimentos), erro


# Monta o prompt, incluindo RAG e/ou memoria quando ativados.
def montar_prompt(erros, contexto_rag=None):
    prompt = (
        f"Resolva a Torre de Hanói com {DISCOS} discos. Os pinos são A, B e C, "
        "todos os discos começam em A e devem terminar em C."
    )
    if USAR_RAG and contexto_rag:
        prompt += (
            "\n\nConhecimentos recuperados sobre a Torre de Hanói:\n"
            + contexto_rag
            + "\n\nUse esses conhecimentos como orientação, sem copiar exemplos. "
            "Planeje internamente a escolha da haste auxiliar, mantenha a haste "
            "de destino livre para o maior disco e confira a validade de cada "
            "movimento. Não escreva o planejamento.\n"
        )
    prompt += (
        " Responda só com os movimentos, um por linha, no formato A->C. "
        "Sem explicações."
    )
    if USAR_MEMORIA and erros:
        prompt += (
            "\nNas tentativas anteriores você errou nos movimentos: "
            + ", ".join(erros)
            + ". Confira cada movimento com cuidado para não repetir esses erros."
        )
    return prompt


# Envia o prompt ao Ollama
def perguntar_ollama(modelo, prompt):
    resposta = requests.post(
        OLLAMA_URL,
        json={
            "model": modelo,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0},
        },
        timeout=TIMEOUT,
    )
    resposta.raise_for_status()
    return resposta.json().get("response", "")


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
        f"| memoria: {USAR_MEMORIA} | rag: {USAR_RAG} "
        f"| minimo de movimentos: {minimos}\n"
    )

    for modelo in MODELOS:
        execucao_id = criar_execucao(conn, modelo, DISCOS, REPETICOES, modo)
        print(f"=== {modelo} | execucao #{execucao_id} | modo: {modo} ===")
        tempos = []
        movimentos_ok = []
        acertos = 0
        gravadas = 0

        # Repete o teste para cada modelo.
        for tentativa in range(1, REPETICOES + 1):
            erros = buscar_erros(conn, modelo, DISCOS) if USAR_MEMORIA else []
            prompt = montar_prompt(erros, contexto_rag)

            inicio = time.time()
            try:
                texto = perguntar_ollama(modelo, prompt)
            except requests.exceptions.ConnectionError:
                print("ERRO: o Ollama nao esta rodando em http://localhost:11434.")
                print("Inicie com 'ollama serve' e rode o script de novo.")
                conn.close()
                sys.exit(1)
            except requests.exceptions.ReadTimeout:
                print(f"tentativa {tentativa}/{REPETICOES}: tempo esgotado, pulando...")
                continue
            except requests.exceptions.HTTPError as e:
                if e.response is not None and e.response.status_code == 404:
                    print(f"ERRO: modelo '{modelo}' nao encontrado. Rode: ollama pull {modelo}")
                    break
                print(f"tentativa {tentativa}/{REPETICOES}: erro HTTP ({e}), pulando...")
                continue
            except requests.exceptions.RequestException as e:
                print(f"tentativa {tentativa}/{REPETICOES}: falha no Ollama ({e}), pulando...")
                continue
            tempo = time.time() - inicio

            resolveu, feitos, erro = validar(texto, DISCOS)

            # Grava a tentativa com parametros (%s), nunca concatenando SQL.
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO resultados
                    (data, execucao_id, modelo, discos, tentativa, resolveu,
                     movimentos_feitos, movimentos_minimos, erro_no_movimento,
                     tempo_segundos, usou_memoria)
                VALUES (NOW(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                ),
            )
            conn.commit()
            cursor.close()

            gravadas += 1
            tempos.append(tempo)
            if resolveu:
                acertos += 1
                movimentos_ok.append(feitos)

            status = "OK" if resolveu else f"erro: {erro}"
            print(f"tentativa {tentativa}/{REPETICOES}: {status} | "
                  f"{feitos} movimentos | {tempo:.2f}s")

        # Resumo simples do modelo.
        print()
        if gravadas == 0:
            print(f"Resumo {modelo}: nenhuma tentativa concluida.\n")
            continue

        taxa = acertos / gravadas * 100
        print(f"Acertos: {acertos} de {gravadas} = {taxa:.0f}%")
        if movimentos_ok:
            media = sum(movimentos_ok) / len(movimentos_ok)
            print(f"Media de movimentos (acertos): {media:.1f} | minimo: {minimos}")
        else:
            print("Media de movimentos (acertos): sem acertos")
        print(f"Tempo medio: {sum(tempos) / len(tempos):.2f}s\n")

    conn.close()


if __name__ == "__main__":
    main()
