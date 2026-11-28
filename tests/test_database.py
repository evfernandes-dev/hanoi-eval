import json
import unittest

import database


class FakeCursor:
    def __init__(self, log, lastrowid=42):
        self.log = log
        self.lastrowid = lastrowid
        self.closed = False

    def execute(self, sql, params=None):
        self.log.append((sql, params))

    def close(self):
        self.closed = True


class FakeConn:
    def __init__(self):
        self.log = []
        self.commits = 0

    def cursor(self):
        return FakeCursor(self.log)

    def commit(self):
        self.commits += 1


class RegistrarResultadoTest(unittest.TestCase):
    def test_grava_com_discos_passados_e_chunks_no_lugar_certo(self):
        conn = FakeConn()
        database.registrar_resultado(
            conn,
            execucao_id=7,
            modelo="qwen2.5:3b",
            discos=4,
            tentativa=2,
            rodada=3,
            resolveu=True,
            movimentos_feitos=15,
            movimentos_minimos=15,
            erro="x" * 300,
            tempo_segundos=1.234,
            status="ok",
            prompt="prompt",
            resposta_bruta="A->C",
            estado_final={"A": [], "B": [], "C": [4, 3, 2, 1]},
            chunks=[{"documento": "regras.md", "score": 0.9}],
            temperatura=0.5,
            seed=1000,
            usou_rag=True,
        )

        self.assertEqual(conn.commits, 1)
        sql, params = conn.log[-1]
        self.assertIn("INSERT INTO resultados", sql)
        self.assertEqual(params["discos"], 4)
        self.assertEqual(params["execucao_id"], 7)
        self.assertEqual(params["rodada"], 3)
        self.assertEqual(params["resolveu"], 1)
        self.assertEqual(params["usou_memoria"], 0)
        self.assertEqual(params["usou_rag"], 1)
        self.assertEqual(params["temperatura"], 0.5)
        self.assertEqual(params["seed"], 1000)
        self.assertEqual(len(params["erro_no_movimento"]), 255)
        self.assertEqual(
            json.loads(params["estado_final"]),
            {"A": [], "B": [], "C": [4, 3, 2, 1]},
        )
        self.assertEqual(
            json.loads(params["chunks"]),
            [{"documento": "regras.md", "score": 0.9}],
        )

    def test_nao_usa_discos_global(self):
        import config

        original = config.DISCOS_PADRAO
        try:
            config.DISCOS_PADRAO = 3
            conn = FakeConn()
            database.registrar_resultado(
                conn,
                execucao_id=1,
                modelo="m",
                discos=4,
                tentativa=1,
                rodada=1,
                resolveu=False,
                movimentos_feitos=0,
                movimentos_minimos=15,
                erro=None,
                tempo_segundos=0.1,
                status="timeout",
                prompt="p",
                resposta_bruta=None,
                estado_final=None,
            )
            _, params = conn.log[-1]
            self.assertEqual(params["discos"], 4)
        finally:
            config.DISCOS_PADRAO = original

    def test_campos_opcionais_ficam_none(self):
        conn = FakeConn()
        database.registrar_resultado(
            conn,
            execucao_id=1,
            modelo="m",
            discos=3,
            tentativa=1,
            rodada=1,
            resolveu=False,
            movimentos_feitos=0,
            movimentos_minimos=7,
            erro=None,
            tempo_segundos=0.1,
            status="erro_ollama",
            prompt="p",
            resposta_bruta=None,
            estado_final=None,
        )
        _, params = conn.log[-1]
        self.assertIsNone(params["chunks"])
        self.assertIsNone(params["estado_final"])
        self.assertIsNone(params["temperatura"])
        self.assertIsNone(params["seed"])
        self.assertEqual(params["usou_rag"], 0)


class CriarExecucaoTest(unittest.TestCase):
    def test_cria_e_devolve_id(self):
        conn = FakeConn()
        execucao_id = database.criar_execucao(
            conn,
            modelo="qwen2.5:3b",
            discos=4,
            repeticoes=10,
            modo="blocos",
            modelo_digest="abc",
            prompt_versao="v5",
            rag_versao=None,
        )
        self.assertEqual(execucao_id, 42)
        self.assertEqual(conn.commits, 1)
        sql, params = conn.log[-1]
        self.assertIn("INSERT INTO execucoes", sql)
        self.assertEqual(params["modo"], "blocos")
        self.assertEqual(params["discos"], 4)
        self.assertIsNone(params["rag_versao"])


if __name__ == "__main__":
    unittest.main()
