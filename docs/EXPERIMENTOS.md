# Experimentos

## Pergunta

Contexto externo (RAG) e decomposição de tarefas ajudam um LLM local de 3B a resolver a Torre de Hanói com 4 discos?

## Estratégias comparadas

| Estratégia | Chamadas por tentativa | Contexto | Estado entre chamadas |
|---|---:|---|---|
| `baseline` | 1 | nenhum | não |
| `rag` | 1 | regras + estratégia + composição | não |
| `blocos` | variável (mínimo `2^N - 1`) | decomposição no prompt | sim |

As três usam o mesmo modelo, temperatura, seeds, validador e banco. Os resultados são gravados em execuções separadas (`modo` diferente) e não devem ser misturados.

## Controles

- O validador é independente do modelo.
- O corpus do RAG novo não contém gabaritos de 3 ou 4 discos.
- Na estratégia de blocos, o modelo não recebe os blocos prontos; ele escolhe um movimento por chamada, com o estado atual e o objetivo da etapa.
- O estado-alvo de cada bloco é calculado pelo plano mínimo determinístico e conferido após a resposta.
- Cada tentativa tem uma seed própria e é registrada com prompt e resposta brutos.

## Métricas

- **Acertos por tentativa**: a torre inteira termina em C na ordem correta.
- **Movimentos nos acertos**: média; o mínimo é `2^N - 1`.
- **Tempo por tentativa válida**.
- **Blocos concluídos** (só em `blocos`): quantas tentativas concluíram o bloco 1, o bloco 2 e o bloco 3.
- **Respostas distintas**: com temperatura 0,5, duas tentativas podem gerar a mesma resposta; o n efetivo é no máximo o número de respostas distintas.
- **Falhas de infraestrutura**: timeout, Ollama offline, modelo ausente e HTTP; ficam fora da taxa de acerto, mas permanecem no banco.

## Resultados históricos (v1–v4)

O banco preserva 47 execuções e 388 registros do laboratório anterior (ids 1–47). As execuções #48–#52 são testes de fumaça do código novo, com uma repetição por estratégia; servem para verificar o fluxo, não como resultado científico. As execuções #49 e #51 usam a primeira versão do runner de blocos (uma chamada por bloco); a #52 usa a versão atual (uma chamada por movimento). No smoke test #52 (3 discos), o modelo repetiu `A->C` e fez um lance ilegal no bloco 1. Resumo histórico:

| Evidência | Resultado |
|---|---:|
| Registros de 4 discos | 173 |
| Acertos em 4 discos | **0** |
| Respostas válidas de v4a/v4b com estado final `A=[] B=[3,2] C=[4,1]` | 11 de 13 |
| Erros no lance 10 (“pino A vazio”) em v4a/v4b | 11 de 13 |
| R4 (gabarito 3D) | 10/10, uma única resposta |
| Single-shot `v2` 3D sem R4 | 6/80 nominais, 2 respostas distintas corretas |
| `formato_invalido` | 0 |
| `lance_ilegal` / `torre_incompleta` / `ok` / `timeout` | 214 / 85 / 88 / 1 |

O padrão de falha em 4 discos é específico: o modelo acerta o bloco 1 e o lance do meio, mas repete o padrão do bloco 1 (`A->B`, `A->C`, ...) em vez de executar o bloco 2 a partir de B. O estado final errado se repete mesmo com seeds diferentes. O v3a/v3b (estado a cada chamada) resolve 3 discos em 8/10 e 9/10, mas 0/10 em 4 discos.

O RAG antigo recuperava o conteúdo certo, mas o corpus tinha gabaritos literais. No R4, o chunk `gabarito_3_discos_A_para_C.md` foi recuperado e o modelo copiou a sequência 10/10. No B2, os 4 acertos nominais em 3D eram a mesma resposta correta repetida. O v4a entregava os blocos literais e pedia para copiar; ainda assim, 0/13 em 4D. Portanto, o gargalo não é a recuperação: é a composição e a troca de papéis.

## O que os números antigos não provam

- As execuções antigas usaram temperaturas e seeds diferentes; parte delas sofreu pseudo-replicação (temperatura 0 sem seed).
- Os corpora antigos continham gabaritos, o que confunde “RAG” com “copiar resposta”.
- A métrica antiga “tolerante” era redundante: no banco, `resolveu=1` só aparece com `status='ok'`.
- Em algumas linhas antigas, `movimentos_feitos` conta movimentos parseados depois do erro; o código novo conta apenas os aplicados.
- Não houve controle positivo (modelo maior ou solver determinístico). Não sabemos se o harness detectaria sucesso em 4 discos porque nenhum braço produziu sucesso.

## Protocolo novo

Rodar as três estratégias com os mesmos discos, repetições e seeds:

```bash
python hanoi_eval.py --estrategia baseline --discos 3 --repeticoes 10
python hanoi_eval.py --estrategia rag      --discos 3 --repeticoes 10
python hanoi_eval.py --estrategia blocos   --discos 3 --repeticoes 10

python hanoi_eval.py --estrategia baseline --discos 4 --repeticoes 10
python hanoi_eval.py --estrategia rag      --discos 4 --repeticoes 10
python hanoi_eval.py --estrategia blocos   --discos 4 --repeticoes 10
```

O teste honesto é 4 discos. 3 discos serve para calibrar o harness e comparar com o histórico.

## Como interpretar

- Se `blocos` acertar 4 discos e `baseline`/`rag` não, há evidência de que a decomposição ajuda — desde que o número de respostas distintas seja reportado.
- Se o RAG não superar o baseline, o resultado é negativo: recuperar regras não basta para o modelo aplicar a recursão.
- Se nada acertar 4 discos, o resultado também é útil: o limite está na capacidade de composição do modelo, não no corpus.
- Sempre reporte o n efetivo (respostas distintas), não apenas o n nominal.
- Não compare diretamente com a tabela histórica: prompt, temperatura e corpus mudaram.

## Ameaças à validade

- Um único modelo (3B), uma tarefa, `n=10`.
- Sensibilidade ao prompt: mudanças pequenas podem alterar a taxa.
- O corpus do RAG é pequeno e escrito à mão.
- O plano-alvo dos blocos é determinístico, mas o modelo ainda pode usar uma sequência legal diferente e atingir o mesmo estado; isso é aceito.
- O julgamento de “raciocínio” não é automático: cópia de gabarito não conta, e por isso os gabaritos foram removidos do corpus.
