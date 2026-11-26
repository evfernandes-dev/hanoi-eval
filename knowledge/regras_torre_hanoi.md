# Regras da Torre de Hanói

## Objetivo

A Torre de Hanói tem três hastes: A, B e C. No início, todos os n discos estão
empilhados em A, do maior para o menor, com o menor no topo. O objetivo é mover
a torre inteira para C, mantendo a mesma ordem.

## Regras dos movimentos

- Apenas um disco pode ser movido por vez.
- Só o disco do topo de uma haste pode ser movido.
- Um disco pode ir para uma haste vazia ou sobre um disco maior.
- Nunca coloque um disco maior sobre um disco menor.
- A notação de um movimento é X->Y, da haste X para a haste Y.

## Quantidade mínima de movimentos

| discos | mínimo |
|---:|---:|
| 1 | 1 |
| 2 | 3 |
| 3 | 7 |
| 4 | 15 |
| 5 | 31 |

O mínimo para n discos é 2^n - 1. Uma solução com mais movimentos pode ser
válida, mas não é ótima. Só pare quando TODOS os discos estiverem na haste de
destino, na ordem correta.

## Formato da resposta

- Escreva um movimento por linha, no formato X->Y.
- Não encadeie duas ou mais hastes na mesma linha; cada linha deve conter um
  único X->Y.
- Não escreva explicações junto dos movimentos.

## Conferência antes de cada movimento

1. A haste de origem não está vazia.
2. O disco movido é o que está no topo da origem.
3. A haste de destino está vazia ou o disco no topo é maior.
4. Ao final, todos os discos devem estar na haste de destino, em ordem.
