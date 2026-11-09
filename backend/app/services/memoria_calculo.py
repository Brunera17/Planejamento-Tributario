"""Memória de cálculo da simulação: guardada só na tabela memoria_calculo.

Antes ela era gravada duas vezes: nas linhas de memoria_calculo e dentro do resultado_json, que toda leitura do
resultado (tela, dashboard, Excel, PDF) desserializava inteiro. Agora as simulações novas gravam o resultado_json sem
a chave "memoria"; quem precisa dos passos lê daqui, no mesmo formato de antes.

Duas consequências, ambas pequenas:
- A coluna guarda 8 casas decimais e o motor gera até 10: os passos das simulações novas saem com 8 casas (a
  diferença está no 9º decimal e não aparece em nenhum valor exibido).
- As simulações antigas continuam com a memória dentro do JSON, e a leitura usa o JSON delas, com as 10 casas de
  sempre. Não há migração: pela mesma diferença de casas, a tabela quase nunca reconstrói a memória antiga
  exatamente, e reescrever o JSON de todas as simulações perderia esses decimais para quase nada ganhar.
"""
from __future__ import annotations

import json
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.serializacao import para_json

CHAVE = "memoria"
CASAS = Decimal("1E-8")  # escala de memoria_calculo.resultado; igual em SQLite e Postgres

_SQL_PASSOS = text("SELECT secao, descricao, formula, resultado, competencia, fundamento "
                   "FROM memoria_calculo WHERE simulacao_id = :sid ORDER BY ordem")


def _passo(secao, descricao, formula, resultado, competencia, fundamento) -> dict:
    # mesma ordem de chaves e mesma conversão de para_json(PassoMemoria)
    valor = (resultado if isinstance(resultado, Decimal) else Decimal(str(resultado))).quantize(CASAS, ROUND_HALF_UP)
    return {"secao": secao, "descricao": descricao, "formula": formula, "valor": para_json(valor),
            "competencia": competencia, "fundamento": fundamento}


def passos(db: Session, sim) -> list[dict]:
    """Passos da memória de uma simulação, no formato que a API sempre devolveu."""
    if f'"{CHAVE}"' in sim.resultado_json:  # só as antigas; as novas nem chegam a ser desserializadas aqui
        antiga = json.loads(sim.resultado_json).get(CHAVE)
        if antiga is not None:
            return antiga.get("passos", [])
    return [_passo(*linha) for linha in db.execute(_SQL_PASSOS, {"sid": sim.id})]


def sem_memoria(resultado: dict) -> dict:
    return {k: v for k, v in resultado.items() if k != CHAVE}
