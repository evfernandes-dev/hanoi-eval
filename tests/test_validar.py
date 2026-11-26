import json
import unittest

from hanoi_eval import validar

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


class ValidarTest(unittest.TestCase):
    def test_solucao_canonica(self):
        resolveu, feitos, erro, status, estado = validar(SOLUCAO, 3)
        self.assertTrue(resolveu)
        self.assertEqual(feitos, 7)
        self.assertIsNone(erro)
        self.assertEqual(status, "ok")
        self.assertEqual(
            json.loads(estado), {"A": [], "B": [], "C": [3, 2, 1]}
        )

    def test_um_disco(self):
        resolveu, feitos, erro, status, estado = validar("A->C", 1)
        self.assertTrue(resolveu)
        self.assertEqual(feitos, 1)
        self.assertEqual(status, "ok")
        self.assertEqual(json.loads(estado), {"A": [], "B": [], "C": [1]})

    def test_linhas_numeradas(self):
        texto = "\n".join(
            f"{i}. {mov}" for i, mov in enumerate(SOLUCAO.splitlines(), 1)
        )
        resolveu, feitos, erro, status, estado = validar(texto, 3)
        self.assertTrue(resolveu)
        self.assertEqual(feitos, 7)
        self.assertEqual(status, "ok")

    def test_bullets(self):
        for marcador in ("-", "*", "•"):
            texto = "\n".join(
                f"{marcador} {mov}" for mov in SOLUCAO.splitlines()
            )
            self.assertTrue(validar(texto, 3)[0], marcador)

    def test_movimentos_inline(self):
        texto = ", ".join(SOLUCAO.splitlines())
        resolveu, feitos, erro, status, estado = validar(texto, 3)
        self.assertTrue(resolveu)
        self.assertEqual(feitos, 7)

    def test_prefixo_passo(self):
        texto = "\n".join(
            f"Passo {i}: {mov}"
            for i, mov in enumerate(SOLUCAO.splitlines(), 1)
        )
        resolveu, feitos, erro, status, estado = validar(texto, 3)
        self.assertTrue(resolveu)
        self.assertEqual(feitos, 7)

    def test_minusculas_e_setas_variadas(self):
        self.assertTrue(validar(SOLUCAO.replace("->", " → ").lower(), 3)[0])
        self.assertTrue(validar(SOLUCAO.replace("->", "=>"), 3)[0])

    def test_movimento_ilegal(self):
        resolveu, feitos, erro, status, estado = validar("A->B\nA->B", 3)
        self.assertFalse(resolveu)
        self.assertEqual(feitos, 2)
        self.assertEqual(erro, "2 (disco 2 sobre disco 1)")
        self.assertEqual(status, "lance_ilegal")
        self.assertEqual(
            json.loads(estado), {"A": [3, 2], "B": [1], "C": []}
        )

    def test_pino_vazio(self):
        resolveu, feitos, erro, status, estado = validar("B->C", 3)
        self.assertFalse(resolveu)
        self.assertEqual(erro, "1 (pino B vazio)")
        self.assertEqual(status, "lance_ilegal")
        self.assertEqual(
            json.loads(estado), {"A": [3, 2, 1], "B": [], "C": []}
        )

    def test_torre_incompleta(self):
        resolveu, feitos, erro, status, estado = validar(INCOMPLETA_7, 3)
        self.assertFalse(resolveu)
        self.assertEqual(feitos, 7)
        self.assertEqual(erro, "8 (torre incompleta)")
        self.assertEqual(status, "torre_incompleta")
        self.assertEqual(
            json.loads(estado), {"A": [], "B": [3, 2, 1], "C": []}
        )

    def test_movimento_sem_efeito_nao_conta(self):
        texto = SOLUCAO.replace("A->B", "A->A\nA->B", 1)
        resolveu, feitos, erro, status, estado = validar(texto, 3)
        self.assertTrue(resolveu)
        self.assertEqual(feitos, 7)

    def test_apenas_movimento_sem_efeito(self):
        resolveu, feitos, erro, status, estado = validar("A->A", 3)
        self.assertFalse(resolveu)
        self.assertEqual(feitos, 0)
        self.assertEqual(status, "torre_incompleta")
        self.assertEqual(
            json.loads(estado), {"A": [3, 2, 1], "B": [], "C": []}
        )

    def test_sem_movimentos(self):
        for texto in ("", "   \n\t", "Não sei resolver.", "A->D"):
            resolveu, feitos, erro, status, estado = validar(texto, 3)
            self.assertFalse(resolveu)
            self.assertEqual(feitos, 0)
            self.assertEqual(status, "formato_invalido")
            self.assertIn("formato inválido", erro)
            self.assertIsNone(estado)

    def test_explicacao_extra_e_ignorada(self):
        texto = "Vou resolver passo a passo.\n" + SOLUCAO + "\nFim."
        resolveu, feitos, erro, status, estado = validar(texto, 3)
        self.assertTrue(resolveu)
        self.assertEqual(feitos, 7)


if __name__ == "__main__":
    unittest.main()
