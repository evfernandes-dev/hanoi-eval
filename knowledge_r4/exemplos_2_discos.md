# Exemplos resolvidos pequenos

## Exemplo 1 disco de A para C (auxiliar B)

A->C
Estado depois do lance: A=[], B=[], C=[1].

## Exemplo 2 discos de A para C (auxiliar B)

A->B
Estado depois do lance: A=[2], B=[1], C=[].
A->C
Estado depois do lance: A=[], B=[1], C=[2].
B->C
Estado depois do lance: A=[], B=[], C=[2, 1].

## Exemplo 2 discos de A para B (auxiliar C)

A->C
Estado depois do lance: A=[2], B=[], C=[1].
A->B
Estado depois do lance: A=[], B=[2], C=[1].
C->B
Estado depois do lance: A=[], B=[2, 1], C=[].

## Exemplo 2 discos de B para C (auxiliar A)

B->A
Estado depois do lance: A=[1], B=[2], C=[].
B->C
Estado depois do lance: A=[1], B=[], C=[2].
A->C
Estado depois do lance: A=[], B=[], C=[2, 1].
