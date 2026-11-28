# Composição abstrata de blocos

N discos de X para Y = (N-1 discos de X para Z) + (disco N de X para Y) + (N-1 discos de Z para Y).

No primeiro bloco, Z é a haste auxiliar; no terceiro bloco, X é a haste auxiliar. O disco N é o maior e se move uma única vez.

Ao terminar o primeiro bloco, os n-1 discos menores estão na haste auxiliar e o maior continua sozinho na origem. Só então mova o maior para o destino. Ao terminar o segundo bloco, o maior está no destino e os n-1 menores estão na auxiliar; mova-os para o destino. Confira o estado após cada bloco antes de começar o seguinte.
