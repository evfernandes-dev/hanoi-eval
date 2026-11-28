# Estudos

Conceitos que você precisa saber para explicar o projeto em uma entrevista.

## Torre de Hanói e recursão

- O mínimo é `2^N - 1`; para 3 discos, 7; para 4, 15.
- A solução recursiva tem três passos: mover N-1 para a auxiliar, mover o maior para o destino, mover N-1 da auxiliar para o destino.
- Os papéis (origem, auxiliar, destino) mudam em cada subproblema. O erro do modelo em 4 discos é justamente não trocar esses papéis no bloco 2.
- Entenda por que o maior disco se move uma única vez e por que a torre precisa terminar ordenada.

## LLM local e amostragem

- `temperature`: controla a aleatoriedade. Temperatura 0 é quase determinística; repetir N vezes com temperatura 0 não gera N amostras independentes.
- `seed`: fixa a sequência de amostragem. Seeds diferentes + temperatura > 0 geram amostras diferentes e reproduzíveis.
- Pseudo-replicação: contar a mesma resposta como vários acertos. Sempre reporte respostas distintas.
- Contexto: o modelo não “lembra” entre chamadas; o estado precisa ser escrito no prompt.
- Limitação de modelos pequenos: seguir formato é fácil; manter uma pilha recursiva e trocar papéis é difícil.

## Prompt engineering

- Prompt base: tarefa, regras, formato de saída e instrução para não explicar.
- RAG: inserir conhecimento recuperado antes da tarefa.
- Decomposição: dividir o problema em subproblemas e dar o estado atual.
- Feedback de estado: mostrar o estado depois de cada jogada (usado no v3 antigo; resolve 3 discos, não 4).
- A diferença entre “o modelo sabe a regra” e “o modelo aplica a regra” é central neste projeto.

## RAG

- Chunking: dividir documentos por seções de markdown para não separar título e conteúdo.
- Embedding: vetor que representa o texto; `nomic-embed-text` roda no Ollama.
- Similaridade de cosseno: mede o ângulo entre vetores; quanto mais perto de 1, mais parecidos.
- Top-k: recuperar os k trechos mais similares.
- Qualidade da recuperação ≠ uso da informação. O R4 antigo provou que o modelo copia o gabarito quando ele está no corpus.
- Controle de cópia: se o corpus contém a resposta literal, o experimento mede cópia, não raciocínio. Por isso o corpus novo não tem gabaritos.

## Avaliação

- Taxa de sucesso por tentativa, com numerador e denominador explícitos.
- Intervalo de confiança de Wilson para proporções (especialmente com n pequeno).
- Teste pareado por seed (McNemar exato) quando as mesmas seeds são usadas em duas estratégias.
- Múltiplas comparações: testar muitas condições sem correção aumenta falso positivo.
- n efetivo: número de respostas distintas; com temperatura 0, o n efetivo pode ser 1.
- Resultado negativo também é resultado: “RAG não ajudou” é uma conclusão válida se o experimento for justo.
- Validador independente: nunca aceitar “resolvi” do modelo; simular as jogadas.

## Ollama

- `/api/generate`: geração de texto; opções `temperature` e `seed`.
- `/api/embed`: embeddings.
- `/api/tags`: lista de modelos instalados e digests.
- Timeout e conexão recusada são falhas diferentes: uma permite continuar, a outra não.

## MySQL

- Tabelas `execucoes`, `resultados` e `rag_trechos`.
- Migração aditiva: `ALTER TABLE ... ADD COLUMN`; nunca apagar histórico.
- `utf8mb4` para acentos e caracteres especiais.
- Uma linha por chamada; `rodada` identifica a etapa nos blocos.
- `resolveu` é global; `status` é o resultado daquela chamada.
- Transações e commits: cada registro é persistido mesmo quando a chamada falha.

## Python

- `dataclasses` para resultados claros (`Resultado`, `Aplicacao`, `Tentativa`).
- `unittest` e `unittest.mock` para testar sem Ollama e sem MySQL.
- Separação de responsabilidades: configuração, banco, RAG, validador e runner.
- Argumentos nomeados (`keyword-only`) para evitar bugs de posição, como o antigo `chunks_info` caindo em `estado_final`.

## Como explicar em uma entrevista

1. O problema é composição recursiva, não formato: o modelo de 3B acerta 3 discos e falha ao trocar os papéis no bloco 2 de 4 discos.
2. O validador determinístico garante que o resultado não depende da autoavaliação do modelo.
3. O RAG antigo recuperava bem, mas o corpus tinha gabaritos; o novo mede conhecimento procedural.
4. A estratégia de blocos isola a decomposição: uma chamada por movimento, com estado carregado e alvo verificado.
5. O experimento é pequeno e honesto: reporta n nominal e n efetivo, mantém resultados negativos e não mistura estratégias.
