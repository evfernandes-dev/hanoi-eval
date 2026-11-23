# Regras da Torre de Hanói

## Objetivo

A Torre de Hanói é um quebra-cabeça com três pinos, normalmente chamados A, B e C.
No início, todos os discos estão empilhados no pino A, do maior para o menor,
com o menor no topo. O objetivo é mover a torre inteira para o pino C, mantendo
a mesma ordem: disco maior embaixo e disco menor em cima.

## Regras dos movimentos

- Em cada movimento, apenas um disco pode ser movido.
- Só é permitido mover o disco que está no topo de um pino.
- Um disco pode ser colocado em um pino vazio ou sobre um disco maior.
- Nunca coloque um disco maior sobre um disco menor.
- Os pinos A, B e C podem ser usados como apoio.
- A notação de um movimento é origem->destino, por exemplo A->B.

## Restrições dos discos

- Os discos têm tamanhos diferentes e não podem ser trocados de posição na pilha.
- A ordem em qualquer pino deve ser sempre do maior, na base, para o menor, no topo.
- O disco menor pode ficar sobre qualquer disco maior; o contrário é inválido.
- Um pino vazio pode receber qualquer disco.
- Um movimento para o mesmo pino não altera a configuração.

## Quantidade mínima de movimentos

Para n discos, a quantidade mínima de movimentos é 2^n - 1:

- 1 disco: 1 movimento.
- 2 discos: 3 movimentos.
- 3 discos: 7 movimentos.
- 4 discos: 15 movimentos.

Uma solução com menos movimentos que esse valor é impossível.
Uma solução com mais movimentos pode ser válida, mas não é ótima.

## Como verificar uma solução

1. Comece com todos os discos no pino A, em ordem.
2. Leia um movimento por linha, no formato A->C.
3. Confira se o pino de origem não está vazio.
4. Confira se o disco movido é o que está no topo do pino de origem.
5. Confira se o pino de destino está vazio ou se o disco do topo é maior.
6. Ao final, todos os discos devem estar no pino C, do maior para o menor.
7. Conte os movimentos: para 3 discos, o mínimo é 7.

## Erros comuns

- Tentar mover um disco maior sobre um disco menor.
- Tentar retirar um disco de um pino vazio.
- Mover um disco que não está no topo da pilha.
- Terminar com discos em B ou com a torre fora de ordem.
- Escrever movimentos em formato diferente de A->C.
