# Estratégias para resolver a Torre de Hanói

## Pensar em subproblemas

Para mover uma torre com n discos de uma haste de origem para uma haste de destino, não tente resolver tudo de uma vez. Divida o problema em três partes:

1. Mova os n-1 discos menores para a haste auxiliar.
2. Mova o maior disco para a haste de destino.
3. Mova os n-1 discos da haste auxiliar para a haste de destino.

Cada parte é uma Torre de Hanói menor. A mesma ideia se repete até sobrar um único disco.

## Escolher a haste auxiliar

Com três hastes (A, B e C), a haste auxiliar é a que não é origem nem destino. Ao mover a torre de A para C, a haste auxiliar é B. Ao mover os discos menores de A para B, a haste auxiliar passa a ser C.

Identificar corretamente a haste auxiliar é essencial: os discos menores devem ficar nela, e não na haste de destino, enquanto o maior disco ainda precisa se mover.

## Liberar a haste de destino

O maior disco precisa chegar à haste de destino. Por isso, antes de mover o maior disco, todos os discos menores devem estar fora da haste de destino.

Não coloque os discos menores na haste de destino cedo demais. Use a haste auxiliar para guardá-los e deixe o caminho livre para o maior disco. Só depois traga os menores para o destino.

## Usar a terceira haste

A terceira haste serve como área de manobra. Em cada subproblema, as funções das hastes mudam:

- origem: de onde os discos saem;
- destino: para onde devem ir;
- auxiliar: onde os discos menores ficam temporariamente.

Uma haste que é destino em um passo pode ser auxiliar em outro. Antes de mover, identifique o papel de cada haste naquela etapa.

## Exemplo completo com dois discos

Estado inicial: disco 2 (maior) e disco 1 (menor) em A; B e C vazias. Objetivo: levar os dois discos para C.

1. Mova o disco menor de A para B, a haste auxiliar: `A->B`.
2. Mova o disco maior de A para C, a haste de destino: `A->C`.
3. Mova o disco menor de B para C: `B->C`.

A torre termina em C com 3 movimentos, o mínimo para dois discos. A haste auxiliar B guardou o disco menor enquanto o maior se movia.

## Generalizar para mais discos

A solução para n discos usa a solução para n-1 discos duas vezes. Para 3 discos, primeiro transfira os 2 discos menores de A para B, usando C como auxiliar. Depois mova o disco maior de A para C. Por fim, transfira os 2 discos menores de B para C, usando A como auxiliar.

Não é necessário memorizar a sequência de 3 discos: siga a divisão em subproblemas e escolha a auxiliar correta em cada etapa. Para n discos, o número mínimo de movimentos é 2^n - 1.

## Verificar antes de cada movimento

Antes de escrever cada movimento, confira:

1. A haste de origem não está vazia.
2. O disco retirado é o que está no topo da origem.
3. A haste de destino está vazia ou o disco no topo é maior que o disco movido.
4. A jogada não coloca um disco maior sobre um menor.
5. Após a jogada, o maior disco ainda pode chegar à haste de destino.
6. No final, todos os discos devem estar na haste de destino, em ordem.

Se uma jogada bloquear a haste de destino antes de o maior disco chegar, o plano está errado. Volte ao subproblema e escolha a haste auxiliar corretamente.
