import json
import unittest

import validator

SOLUCAO = """A->C
A->B
C->B
A->C
B->A
B->C
A->C"""

INCOMPLETA_7 = """A->B
A->C
B->C
A->B
C->A
C->B
A->B"""

BLOCO_1_3D = """A->C
A->B
C->B"""

BLOCO_2_3D = "A->C"

BLOCO_3_3D = """B->A
B->C
A->C"""


class ValidatorTest(unittest.TestCase):
    def test_solucao_canonica(self):
        resultado = validator.validar_torre(SOLUCAO, 3)
        self.assertTrue(resultado.resolveu)
        self.assertEqual(resultado.movimentos, 7)
        self.assertIsNone(resultado.erro)
        self.assertEqual(resultado.status, "ok")
        self.assertEqual(
            json.loads(resultado.estado_final), {"A": [], "B": [], "C": [3, 2, 1]}
        )

    def test_um_disco(self):
        resultado = validator.validar_torre("A->C", 1)
        self.assertTrue(resultado.resolveu)
        self.assertEqual(resultado.movimentos, 1)
        self.assertEqual(resultado.status, "ok")

    def test_linhas_numeradas(self):
        texto = "\n".join(
            f"{i}. {mov}" for i, mov in enumerate(SOLUCAO.splitlines(), 1)
        )
        resultado = validator.validar_torre(texto, 3)
        self.assertTrue(resultado.resolveu)
        self.assertEqual(resultado.movimentos, 7)

    def test_bullets(self):
        for marcador in ("-", "*", "•"):
            texto = "\n".join(
                f"{marcador} {mov}" for mov in SOLUCAO.splitlines()
            )
            self.assertTrue(validator.validar_torre(texto, 3).resolveu, marcador)

    def test_movimentos_inline(self):
        texto = ", ".join(SOLUCAO.splitlines())
        resultado = validator.validar_torre(texto, 3)
        self.assertTrue(resultado.resolveu)
        self.assertEqual(resultado.movimentos, 7)

    def test_prefixo_passo(self):
        texto = "\n".join(
            f"Passo {i}: {mov}"
            for i, mov in enumerate(SOLUCAO.splitlines(), 1)
        )
        resultado = validator.validar_torre(texto, 3)
        self.assertTrue(resultado.resolveu)
        self.assertEqual(resultado.movimentos, 7)

    def test_minusculas_e_setas_variadas(self):
        self.assertTrue(
            validator.validar_torre(SOLUCAO.replace("->", " → ").lower(), 3).resolveu
        )
        self.assertTrue(
            validator.validar_torre(SOLUCAO.replace("->", "=>"), 3).resolveu
        )

    def test_movimento_ilegal_conta_so_os_aplicados(self):
        resultado = validator.validar_torre("A->B\nA->B\nA->B", 3)
        self.assertFalse(resultado.resolveu)
        self.assertEqual(resultado.movimentos, 1)
        self.assertEqual(resultado.erro, "2 (disco 2 sobre disco 1)")
        self.assertEqual(resultado.status, "lance_ilegal")
        self.assertEqual(
            json.loads(resultado.estado_final), {"A": [3, 2], "B": [1], "C": []}
        )

    def test_pino_vazio(self):
        resultado = validator.validar_torre("B->C", 3)
        self.assertFalse(resultado.resolveu)
        self.assertEqual(resultado.movimentos, 0)
        self.assertEqual(resultado.erro, "1 (pino B vazio)")
        self.assertEqual(resultado.status, "lance_ilegal")

    def test_torre_incompleta(self):
        resultado = validator.validar_torre(INCOMPLETA_7, 3)
        self.assertFalse(resultado.resolveu)
        self.assertEqual(resultado.movimentos, 7)
        self.assertEqual(resultado.erro, "8 (torre incompleta)")
        self.assertEqual(resultado.status, "torre_incompleta")
        self.assertEqual(
            json.loads(resultado.estado_final), {"A": [], "B": [3, 2, 1], "C": []}
        )

    def test_movimento_sem_efeito_nao_conta(self):
        texto = SOLUCAO.replace("A->B", "A->A\nA->B", 1)
        resultado = validator.validar_torre(texto, 3)
        self.assertTrue(resultado.resolveu)
        self.assertEqual(resultado.movimentos, 7)

    def test_apenas_movimento_sem_efeito(self):
        resultado = validator.validar_torre("A->A", 3)
        self.assertFalse(resultado.resolveu)
        self.assertEqual(resultado.movimentos, 0)
        self.assertEqual(resultado.status, "torre_incompleta")
        self.assertEqual(resultado.erro, "1 (torre incompleta)")

    def test_sem_movimentos(self):
        for texto in ("", "   \n\t", "Não sei resolver.", "A->D"):
            resultado = validator.validar_torre(texto, 3)
            self.assertFalse(resultado.resolveu, texto)
            self.assertEqual(resultado.movimentos, 0, texto)
            self.assertEqual(resultado.status, "formato_invalido", texto)
            self.assertIn("formato inválido", resultado.erro, texto)
            self.assertEqual(
                json.loads(resultado.estado_final),
                {"A": [3, 2, 1], "B": [], "C": []},
                texto,
            )

    def test_explicacao_extra_e_ignorada(self):
        texto = "Vou resolver passo a passo.\n" + SOLUCAO + "\nFim."
        resultado = validator.validar_torre(texto, 3)
        self.assertTrue(resultado.resolveu)
        self.assertEqual(resultado.movimentos, 7)

    def test_anotacoes_apos_movimento(self):
        texto = """A->C (disco 1)
A->B #2
C->B — passo 3
4) A->C
B->A (movimento 5)
B->C passo 6
A->C #7"""
        resultado = validator.validar_torre(texto, 3)
        self.assertTrue(resultado.resolveu)
        self.assertEqual(resultado.movimentos, 7)

    def test_anotacao_antes_e_multiplos_na_linha(self):
        texto = """Disco 1: A->C
2) A->B | C->B (2 movimentos)
passo 3: A->C, B->A #4
B->C — passo 5
A->C"""
        resultado = validator.validar_torre(texto, 3)
        self.assertTrue(resultado.resolveu)
        self.assertEqual(resultado.movimentos, 7)

    def test_setas_com_espacos(self):
        resultado = validator.validar_torre(
            SOLUCAO.replace("->", " -> "), 3
        )
        self.assertTrue(resultado.resolveu)
        self.assertEqual(resultado.movimentos, 7)

    def test_bullets_com_anotacao(self):
        texto = "\n".join(f"- {mov} #1" for mov in SOLUCAO.splitlines())
        resultado = validator.validar_torre(texto, 3)
        self.assertTrue(resultado.resolveu)
        self.assertEqual(resultado.movimentos, 7)

    def test_texto_aleatorio_com_seta_nao_e_aceito(self):
        for texto in (
            "O disco 1 vai de A->C porque sim",
            "A->C ou A->B",
            "mover A->C",
        ):
            resultado = validator.validar_torre(texto, 3)
            self.assertFalse(resultado.resolveu, texto)
            self.assertEqual(resultado.movimentos, 0, texto)
            self.assertEqual(resultado.status, "formato_invalido", texto)

    def test_cadeia_nao_e_aceita(self):
        resultado = validator.validar_torre("A->B->C", 3)
        self.assertFalse(resultado.resolveu)
        self.assertEqual(resultado.status, "formato_invalido")

    def test_aplicar_sequencia_com_estado_carregado(self):
        estado = validator.estado_inicial(3)

        bloco1 = validator.aplicar_sequencia(BLOCO_1_3D, estado)
        self.assertEqual(bloco1.status, "ok")
        self.assertEqual(bloco1.estado, {"A": [3], "B": [2, 1], "C": []})
        self.assertEqual(bloco1.movimentos, [("A", "C"), ("A", "B"), ("C", "B")])

        bloco2 = validator.aplicar_sequencia(BLOCO_2_3D, bloco1.estado)
        self.assertEqual(bloco2.status, "ok")
        self.assertEqual(bloco2.estado, {"A": [], "B": [2, 1], "C": [3]})

        bloco3 = validator.aplicar_sequencia(BLOCO_3_3D, bloco2.estado)
        self.assertEqual(bloco3.status, "ok")
        self.assertEqual(bloco3.estado, {"A": [], "B": [], "C": [3, 2, 1]})

    def test_aplicar_sequencia_nao_altera_estado_recebido(self):
        estado = validator.estado_inicial(3)
        validator.aplicar_sequencia("A->C", estado)
        self.assertEqual(estado, {"A": [3, 2, 1], "B": [], "C": []})

    def test_estado_inicial_quatro_discos(self):
        self.assertEqual(
            validator.estado_inicial(4),
            {"A": [4, 3, 2, 1], "B": [], "C": []},
        )

    def test_estado_para_texto(self):
        self.assertEqual(
            validator.estado_para_texto(validator.estado_inicial(4)),
            "A=[4,3,2,1] B=[] C=[]",
        )


if __name__ == "__main__":
    unittest.main()
