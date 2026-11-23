# hanoi_eval.py
# Testa modelos locais do Ollama resolvendo a Torre de Hanói.

import requests

# ===== Configuracoes =====
DISCOS = 3
USAR_MEMORIA = False
USAR_RAG = False

OLLAMA_URL = "http://localhost:11434/api/generate"
TIMEOUT = 180


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
