# Estratégias para resolver a Torre de Hanói

## Procedimento por papéis (qualquer número de discos)

Para mover n discos da haste ORIGEM para a haste DESTINO usando a haste
AUXILIAR:

1. Mova n-1 discos da ORIGEM para a AUXILIAR.
2. Mova o maior disco da ORIGEM para o DESTINO.
3. Mova os n-1 discos da AUXILIAR para o DESTINO.

O maior disco se move uma única vez. Cada passo é um subproblema de Torre de
Hanói com os mesmos três papéis, mas aplicados a hastes diferentes.

## Os papéis mudam em cada subproblema

No passo 1, o destino do subproblema é a haste AUXILIAR do problema maior. No
passo 3, a origem do subproblema é a haste AUXILIAR do problema maior. Antes de
cada subproblema, identifique novamente quem é origem, quem é auxiliar e quem é
destino naquela etapa. Os papéis não são fixos entre os níveis da recursão.

## Procedimento para mover 3 discos de A para C usando B como auxiliar

- Origem inicial: A. Destino: C. Auxiliar: B.
- Passo 1: mover 2 discos de A para B, usando C como auxiliar do subproblema.
- Passo 2: mover o maior disco (disco 3) de A para C.
- Passo 3: mover 2 discos de B para C, usando A como auxiliar do subproblema.
- Só pare quando os 3 discos estiverem em C, na ordem [3, 2, 1].

## Procedimento para mover 4 discos de A para C usando B como auxiliar

- Origem inicial: A. Destino: C. Auxiliar: B.
- Passo 1: mover 3 discos de A para B, usando C como auxiliar do subproblema.
- Passo 2: mover o maior disco (disco 4) de A para C.
- Passo 3: mover 3 discos de B para C, usando A como auxiliar do subproblema.
- Só pare quando os 4 discos estiverem em C, na ordem [4, 3, 2, 1].

## Conferência antes de cada jogada

- A origem não está vazia.
- O disco é o que está no topo da origem.
- O destino está vazio ou o disco no topo do destino é maior.
- O maior disco ainda não foi movido; ele deve ir para o destino uma única vez.
- Ao final, todos os discos devem estar no destino, em ordem.
