import json
import unittest

from experimento_rag import avaliar

SOLUCAO = """A->C
A->B
C->B
A->C
B->A
B->C
A->C"""


class AvaliarTest(unittest.TestCase):
    def test_solucao_limpa(self):
        av = avaliar(SOLUCAO, 3)
        self.assertEqual(av["status"], "ok")
        self.assertTrue(av["estrito"])
        self.assertTrue(av["tolerante"])
        self.assertTrue(av["resolveu"])
        self.assertFalse(av["composto"])
        self.assertEqual(
            json.loads(av["estado_final"]),
            {"A": [], "B": [], "C": [3, 2, 1]},
        )

    def test_cadeia_composta(self):
        av = avaliar("A->B->C", 3)
        self.assertEqual(av["status"], "formato_composto")
        self.assertTrue(av["composto"])
        self.assertFalse(av["estrito"])
        self.assertFalse(av["tolerante"])
        self.assertFalse(av["resolveu"])
        self.assertEqual(
            json.loads(av["estado_final"]),
            {"A": [3, 2], "B": [], "C": [1]},
        )

    def test_incompleta_limpa(self):
        av = avaliar("A->C", 3)
        self.assertEqual(av["status"], "torre_incompleta")
        self.assertFalse(av["composto"])
        self.assertFalse(av["resolveu"])

    def test_ilegal_limpa(self):
        av = avaliar("A->B\nA->B", 3)
        self.assertEqual(av["status"], "lance_ilegal")
        self.assertFalse(av["composto"])

    def test_formato_invalido(self):
        av = avaliar("Não sei resolver.", 3)
        self.assertEqual(av["status"], "formato_invalido")
        self.assertIsNone(av["estado_final"])


if __name__ == "__main__":
    unittest.main()
