"""Motor de cálculo do planejamento tributário (funções puras, sem I/O)."""
from .engine import simular
from .tipos import EntradaSimulacao, ResultadoSimulacao

__all__ = ["simular", "EntradaSimulacao", "ResultadoSimulacao"]
