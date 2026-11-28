import json
import unittest
from unittest import mock

import requests

import hanoi_eval
import validator

SOLUCAO = """A->C
A->B
C->B
A->C
B->A
B->C
A->C"""


class RespostaFake:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self.payload = payload or {}
        self.texto = None

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(
                f"HTTP {self.status_code}", response=self
            )

    def json(self):
        return self.payload


class ChamarOllamaTest(unittest.TestCase):
    def test_sucesso_devolve_texto(self):
        resposta = RespostaFake(payload={"response": "A->C"})
        with mock.patch("hanoi_eval.requests.post", return_value=resposta) as post:
            texto = hanoi_eval.chamar_ollama(
                "prompt", temperatura=0.5, seed=1234
            )
        self.assertEqual(texto, "A->C")
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["model"], hanoi_eval.config.MODELO)
        self.assertFalse(payload["stream"])
        self.assertEqual(payload["options"], {"temperature": 0.5, "seed": 1234})

    def test_conexao_indisponivel_e_fatal(self):
        with mock.patch(
            "hanoi_eval.requests.post",
            side_effect=requests.exceptions.ConnectionError("offline"),
        ), self.assertRaises(hanoi_eval.OllamaErro) as contexto:
            hanoi_eval.chamar_ollama("p", temperatura=0.5, seed=1)
        self.assertEqual(contexto.exception.status, "erro_ollama")
        self.assertTrue(contexto.exception.fatal)

    def test_timeout_nao_e_fatal(self):
        with mock.patch(
            "hanoi_eval.requests.post",
            side_effect=requests.exceptions.ReadTimeout("demorou"),
        ), self.assertRaises(hanoi_eval.OllamaErro) as contexto:
            hanoi_eval.chamar_ollama("p", temperatura=0.5, seed=1)
        self.assertEqual(contexto.exception.status, "timeout")
        self.assertFalse(contexto.exception.fatal)

    def test_modelo_ausente_e_fatal(self):
        resposta = RespostaFake(status=404)
        with mock.patch(
            "hanoi_eval.requests.post", return_value=resposta
        ), self.assertRaises(hanoi_eval.OllamaErro) as contexto:
            hanoi_eval.chamar_ollama("p", temperatura=0.5, seed=1)
        self.assertEqual(contexto.exception.status, "modelo_ausente")
        self.assertTrue(contexto.exception.fatal)

    def test_http_erro_nao_e_fatal(self):
        resposta = RespostaFake(status=500)
        with mock.patch(
            "hanoi_eval.requests.post", return_value=resposta
        ), self.assertRaises(hanoi_eval.OllamaErro) as contexto:
            hanoi_eval.chamar_ollama("p", temperatura=0.5, seed=1)
        self.assertEqual(contexto.exception.status, "http_erro")
        self.assertFalse(contexto.exception.fatal)

    def test_request_exception_generica_nao_e_fatal(self):
        with mock.patch(
            "hanoi_eval.requests.post",
            side_effect=requests.exceptions.RequestException("falhou"),
        ), self.assertRaises(hanoi_eval.OllamaErro) as contexto:
            hanoi_eval.chamar_ollama("p", temperatura=0.5, seed=1)
        self.assertEqual(contexto.exception.status, "erro_ollama")
        self.assertFalse(contexto.exception.fatal)


class VerificarModelosTest(unittest.TestCase):
    def test_ollama_offline_retorna_falso(self):
        with mock.patch(
            "hanoi_eval.rag.modelo_instalado",
            side_effect=requests.exceptions.ConnectionError("offline"),
        ):
            self.assertFalse(hanoi_eval.verificar_modelos(False))

    def test_modelo_ausente_retorna_falso(self):
        with mock.patch(
            "hanoi_eval.rag.modelo_instalado", return_value=False
        ):
            self.assertFalse(hanoi_eval.verificar_modelos(False))

    def test_main_para_quando_ollama_esta_offline(self):
        with mock.patch(
            "hanoi_eval.verificar_modelos", return_value=False
        ):
            self.assertEqual(
                hanoi_eval.main(
                    ["--estrategia", "baseline", "--discos", "3", "--repeticoes", "1"]
                ),
                1,
            )


class DecomposicaoTest(unittest.TestCase):
    def test_decompoe_tres_discos(self):
        blocos = hanoi_eval.decompor(3)
        self.assertEqual(
            blocos[0],
            {"k": 2, "origem": "A", "destino": "B", "auxiliar": "C"},
        )
        self.assertEqual(
            blocos[1],
            {"k": 1, "origem": "A", "destino": "C", "auxiliar": "B"},
        )
        self.assertEqual(
            blocos[2],
            {"k": 2, "origem": "B", "destino": "C", "auxiliar": "A"},
        )

    def test_decompoe_um_disco(self):
        self.assertEqual(
            hanoi_eval.decompor(1),
            [{"k": 1, "origem": "A", "destino": "C", "auxiliar": "B"}],
        )

    def test_plano_minimo_resolve(self):
        movimentos = hanoi_eval.plano(3, "A", "C", "B")
        self.assertEqual(len(movimentos), 7)
        estado = validator.aplicar(validator.estado_inicial(3), movimentos)
        self.assertEqual(estado["C"], [3, 2, 1])

    def test_plano_quatro_discos_tem_quinze_movimentos(self):
        self.assertEqual(len(hanoi_eval.plano(4, "A", "C", "B")), 15)

    def test_prompt_de_bloco_descreve_estado_e_etapa(self):
        estado = {"A": [], "B": [3, 2, 1], "C": [4]}
        prompt = hanoi_eval.montar_prompt_bloco(
            4, estado, 3, 3, 3, "B", "C", "A", 0
        )
        self.assertIn("A=[] B=[3,2,1] C=[4]", prompt)
        self.assertIn("Etapa 3 de 3", prompt)
        self.assertIn("mover 3 discos da haste B", prompt)
        self.assertIn("usando A como auxiliar", prompt)
        self.assertIn("Movimentos já feitos nesta etapa: 0", prompt)
        self.assertIn("no mínimo 7", prompt)
        self.assertIn("próximo movimento", prompt)


class ExecutarSimplesTest(unittest.TestCase):
    def test_sucesso_grava_chunks_e_estado(self):
        with mock.patch(
            "hanoi_eval.chamar_ollama", return_value=SOLUCAO
        ), mock.patch(
            "hanoi_eval.database.registrar_resultado"
        ) as registrar:
            tentativa = hanoi_eval.executar_tentativa_simples(
                None, 1, 3, 1, "prompt", 1000, 'chunks-json'
            )

        self.assertTrue(tentativa.sucesso)
        self.assertTrue(tentativa.valida)
        self.assertEqual(tentativa.movimentos, 7)
        parametros = registrar.call_args.kwargs
        self.assertEqual(parametros["discos"], 3)
        self.assertTrue(parametros["resolveu"])
        self.assertEqual(parametros["status"], "ok")
        self.assertEqual(parametros["chunks"], "chunks-json")
        self.assertEqual(parametros["usou_rag"], True)
        self.assertEqual(
            json.loads(parametros["estado_final"])["C"], [3, 2, 1]
        )

    def test_falha_generica_guarda_chunks_em_chunks(self):
        erro = hanoi_eval.OllamaErro("falha", "erro_ollama")
        with mock.patch(
            "hanoi_eval.chamar_ollama", side_effect=erro
        ), mock.patch(
            "hanoi_eval.database.registrar_resultado"
        ) as registrar:
            tentativa = hanoi_eval.executar_tentativa_simples(
                None, 1, 3, 1, "prompt", 1000, 'chunks-json'
            )

        self.assertFalse(tentativa.sucesso)
        self.assertFalse(tentativa.valida)
        parametros = registrar.call_args.kwargs
        self.assertEqual(parametros["chunks"], "chunks-json")
        self.assertIsNone(parametros["estado_final"])
        self.assertIsNone(parametros["resposta_bruta"])
        self.assertEqual(parametros["status"], "erro_ollama")

    def test_falha_fatal_registra_e_propaga(self):
        erro = hanoi_eval.OllamaErro("offline", "erro_ollama", fatal=True)
        with mock.patch(
            "hanoi_eval.chamar_ollama", side_effect=erro
        ), mock.patch(
            "hanoi_eval.database.registrar_resultado"
        ) as registrar, self.assertRaises(hanoi_eval.OllamaErro):
            hanoi_eval.executar_tentativa_simples(
                None, 1, 3, 1, "prompt", 1000, None
            )

        self.assertEqual(registrar.call_count, 1)
        self.assertEqual(registrar.call_args.kwargs["status"], "erro_ollama")


class ExecutarBlocosTest(unittest.TestCase):
    def test_compõe_blocos_com_estado_carregado(self):
        respostas = iter(
            ["A->C", "A->B", "C->B", "A->C", "B->A", "B->C", "A->C"]
        )
        with mock.patch(
            "hanoi_eval.chamar_ollama",
            side_effect=lambda *args, **kwargs: next(respostas),
        ), mock.patch(
            "hanoi_eval.database.registrar_resultado"
        ) as registrar:
            tentativa = hanoi_eval.executar_tentativa_blocos(
                None, 1, 3, 1, 1000
            )

        self.assertTrue(tentativa.sucesso)
        self.assertTrue(tentativa.valida)
        self.assertEqual(tentativa.movimentos, 7)
        self.assertEqual(tentativa.etapas_ok, 3)
        self.assertEqual(registrar.call_count, 7)

        primeira = registrar.call_args_list[0].kwargs
        self.assertEqual(primeira["rodada"], 1)
        self.assertFalse(primeira["resolveu"])
        self.assertEqual(primeira["status"], "ok")
        self.assertEqual(
            json.loads(primeira["estado_final"]),
            {"A": [3, 2], "B": [], "C": [1]},
        )

        fim_bloco_1 = registrar.call_args_list[2].kwargs
        self.assertEqual(fim_bloco_1["rodada"], 1)
        self.assertEqual(
            json.loads(fim_bloco_1["estado_final"]),
            {"A": [3], "B": [2, 1], "C": []},
        )

        ultima = registrar.call_args_list[-1].kwargs
        self.assertEqual(ultima["rodada"], 3)
        self.assertTrue(ultima["resolveu"])
        self.assertEqual(ultima["status"], "ok")
        self.assertEqual(
            json.loads(ultima["estado_final"]),
            {"A": [], "B": [], "C": [3, 2, 1]},
        )

    def test_para_quando_movimento_e_ilegal(self):
        with mock.patch(
            "hanoi_eval.chamar_ollama", return_value="A->B"
        ), mock.patch(
            "hanoi_eval.database.registrar_resultado"
        ) as registrar:
            tentativa = hanoi_eval.executar_tentativa_blocos(
                None, 1, 3, 1, 1000
            )

        self.assertFalse(tentativa.sucesso)
        self.assertTrue(tentativa.valida)
        self.assertEqual(tentativa.etapas_ok, 0)
        self.assertEqual(registrar.call_count, 2)
        parametros = registrar.call_args.kwargs
        self.assertEqual(parametros["status"], "lance_ilegal")
        self.assertIn("disco 2 sobre disco 1", parametros["erro"])

    def test_falha_de_infraestrutura_no_bloco(self):
        erro = hanoi_eval.OllamaErro("timeout", "timeout")
        with mock.patch(
            "hanoi_eval.chamar_ollama", side_effect=erro
        ), mock.patch(
            "hanoi_eval.database.registrar_resultado"
        ) as registrar:
            tentativa = hanoi_eval.executar_tentativa_blocos(
                None, 1, 3, 1, 1000
            )

        self.assertFalse(tentativa.sucesso)
        self.assertFalse(tentativa.valida)
        self.assertEqual(tentativa.etapas_ok, 0)
        self.assertEqual(registrar.call_count, 1)
        self.assertEqual(registrar.call_args.kwargs["status"], "timeout")
        self.assertIsNone(registrar.call_args.kwargs["chunks"])


if __name__ == "__main__":
    unittest.main()
