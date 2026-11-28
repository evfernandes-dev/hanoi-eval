import json
import os
import tempfile
import unittest
from unittest import mock

import rag


class FakeCursor:
    def __init__(self, rows=None, count=0, log=None):
        self.rows = rows or []
        self.count = count
        self.log = log if log is not None else []
        self.closed = False

    def execute(self, sql, params=None):
        self.log.append((sql, params))

    def fetchone(self):
        return (self.count,)

    def fetchall(self):
        return self.rows

    def close(self):
        self.closed = True


class FakeConn:
    def __init__(self, rows=None, count=0):
        self.rows = rows or []
        self.count = count
        self.log = []
        self.commits = 0

    def cursor(self):
        return FakeCursor(self.rows, self.count, self.log)

    def commit(self):
        self.commits += 1


class DividirTest(unittest.TestCase):
    def test_divide_por_secoes(self):
        texto = "# Título\n\nTexto.\n\n## Seção A\n\nConteúdo A.\n\n## Seção B\n\nConteúdo B."
        trechos = rag.dividir_em_trechos(texto)
        self.assertEqual(len(trechos), 3)
        self.assertIn("Título", trechos[0])
        self.assertIn("Conteúdo A", trechos[1])

    def test_ignora_titulo_isolado(self):
        self.assertEqual(rag.dividir_em_trechos("# Só título"), [])

    def test_secao_longa_e_dividida(self):
        texto = "# Longa\n\n" + ("palavra " * 300)
        trechos = rag.dividir_em_trechos(texto, max_caracteres=200)
        self.assertGreater(len(trechos), 1)
        self.assertTrue(all(len(trecho) <= 200 for trecho in trechos))


class SimilaridadeTest(unittest.TestCase):
    def test_vetores_iguais(self):
        self.assertAlmostEqual(rag.similaridade_cosseno([1, 2], [1, 2]), 1.0)

    def test_vetores_ortogonais(self):
        self.assertAlmostEqual(rag.similaridade_cosseno([1, 0], [0, 1]), 0.0)

    def test_vetores_invalidos(self):
        self.assertEqual(rag.similaridade_cosseno([], [1]), 0.0)
        self.assertEqual(rag.similaridade_cosseno([0, 0], [1, 1]), 0.0)


class RanquearTest(unittest.TestCase):
    def test_ordena_e_limita(self):
        trechos = [
            {"id": 1, "texto": "a", "embedding": json.dumps([1, 0])},
            {"id": 2, "texto": "b", "embedding": json.dumps([0, 1])},
            {"id": 3, "texto": "c", "embedding": json.dumps([0.8, 0.2])},
        ]
        resultado = rag.ranquear([1, 0.1], trechos, 2)
        self.assertEqual([t["id"] for t in resultado], [1, 3])


class BuscarTest(unittest.TestCase):
    def test_filtra_hashes_antigos_e_ordena(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = os.path.join(pasta, "doc.md")
            with open(caminho, "w", encoding="utf-8") as arquivo:
                arquivo.write("# Regras\n\nTexto.\n")
            with open(caminho, "r", encoding="utf-8") as arquivo:
                texto = arquivo.read()
            hash_atual = rag.calcular_hash(texto)

            linhas = [
                (1, "doc.md", hash_atual, texto, json.dumps([1.0, 0.0])),
                (2, "doc.md", "hash-antigo", "velho", json.dumps([1.0, 0.0])),
            ]
            conn = FakeConn(rows=linhas)

            with mock.patch(
                "rag.obter_embedding", return_value=[1.0, 0.0]
            ):
                resultado = rag.buscar(
                    conn, "pergunta", "nomic-embed-text", pasta, 3
                )

            self.assertEqual(len(resultado), 1)
            self.assertEqual(resultado[0]["id"], 1)
            self.assertAlmostEqual(resultado[0]["score"], 1.0)

    def test_sem_linhas_retorna_vazio(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = os.path.join(pasta, "doc.md")
            with open(caminho, "w", encoding="utf-8") as arquivo:
                arquivo.write("# Regras\n\nTexto.\n")
            conn = FakeConn(rows=[])
            with mock.patch(
                "rag.obter_embedding", return_value=[1.0, 0.0]
            ):
                self.assertEqual(
                    rag.buscar(conn, "pergunta", "nomic", pasta, 3), []
                )


class IndexarTest(unittest.TestCase):
    def test_indexa_documento_novo(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = os.path.join(pasta, "doc.md")
            with open(caminho, "w", encoding="utf-8") as arquivo:
                arquivo.write("# Regras\n\nTexto.\n")
            conn = FakeConn(count=0)
            with mock.patch(
                "rag.obter_embedding", return_value=[0.1, 0.2]
            ) as embed:
                rag.indexar(conn, pasta, "nomic-embed-text")

            self.assertEqual(embed.call_count, 1)
            inserts = [sql for sql, _ in conn.log if "INSERT" in sql]
            self.assertEqual(len(inserts), 1)
            self.assertEqual(conn.commits, 1)

    def test_pula_documento_ja_indexado(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = os.path.join(pasta, "doc.md")
            with open(caminho, "w", encoding="utf-8") as arquivo:
                arquivo.write("# Regras\n\nTexto.\n")
            conn = FakeConn(count=1)
            with mock.patch("rag.obter_embedding") as embed:
                rag.indexar(conn, pasta, "nomic-embed-text")
            embed.assert_not_called()
            self.assertEqual(conn.commits, 0)


class ContextoTest(unittest.TestCase):
    def test_monta_contexto_numerado(self):
        trechos = [
            {"texto": "primeiro"},
            {"texto": "segundo"},
        ]
        self.assertEqual(
            rag.montar_contexto(trechos),
            "[1] primeiro\n\n[2] segundo",
        )

    def test_versao_corpus_muda_com_conteudo(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = os.path.join(pasta, "doc.md")
            with open(caminho, "w", encoding="utf-8") as arquivo:
                arquivo.write("# A\n\nTexto A.\n")
            primeira = rag.versao_corpus(pasta)
            with open(caminho, "w", encoding="utf-8") as arquivo:
                arquivo.write("# A\n\nTexto B.\n")
            segunda = rag.versao_corpus(pasta)
            self.assertNotEqual(primeira, segunda)
            self.assertLessEqual(len(segunda), 10)

    def test_pergunta_para_discos(self):
        self.assertIn("4 discos", rag.pergunta_para_discos(4))
        self.assertIn("haste A", rag.pergunta_para_discos(4))
        self.assertIn("haste C", rag.pergunta_para_discos(4))


if __name__ == "__main__":
    unittest.main()
