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


