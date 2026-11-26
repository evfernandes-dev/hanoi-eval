# Exemplo de 3 discos com destino diferente do teste

## Exemplo 3 discos de A para B (auxiliar C)

A->B
Estado depois do lance: A=[3, 2], B=[1], C=[].
A->C
Estado depois do lance: A=[3], B=[1], C=[2].
B->C
Estado depois do lance: A=[3], B=[], C=[2, 1].
A->B
Estado depois do lance: A=[], B=[3], C=[2, 1].
C->A
Estado depois do lance: A=[1], B=[3], C=[2].
C->B
Estado depois do lance: A=[1], B=[3, 2], C=[].
A->B
Estado depois do lance: A=[], B=[3, 2, 1], C=[].

## Como reaproveitar quando o destino muda

A estrutura recursiva é a mesma: mova n-1 discos para a auxiliar, mova o maior
disco para o destino e mova os n-1 discos da auxiliar para o destino. Quando o
destino muda, os papéis das hastes mudam. Refaça o procedimento com a nova
origem, o novo destino e a nova auxiliar; não copie a sequência de um exemplo
com destino diferente.
