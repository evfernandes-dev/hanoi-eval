# hanoi_eval.py
# Testa modelos locais do Ollama resolvendo a Torre de Hanói.

import os
import re
import sys

import mysql.connector
import requests

# ===== Configuracoes =====
DISCOS = 3
USAR_MEMORIA = False
USAR_RAG = False

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
