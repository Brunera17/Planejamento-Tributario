"""Importa todos os modelos para registrá-los no metadata (Alembic e create_all)."""
from .cadastro import Empresa, ImportacaoEmpresa, Usuario
from .coleta import (
    Bem,
    CompraMensal,
    CompraOrigem,
    DevolucaoMensal,
    Documento,
    FolhaMensal,
    GrupoDespesa,
    ItemDespesa,
    Levantamento,
    LevantamentoGrupo,
    LevantamentoItem,
    OutraDespesa,
    PesoProgresso,
    TipoDocumento,
)
from .nfe import ImportacaoNfe, NotaFiscal, NotaItem
from .planejamento import HistoricoStatus, Planejamento, PremissaPlanejamento
from .simulacao import MemoriaCalculo, OportunidadeRegistro, RelatorioPdf, Simulacao, SimulacaoResultado
from .tabelas import CfopRegra, NcmRegra, ParametroTributario, ReformaCronograma, SimplesFaixa

__all__ = [
    "Bem", "CfopRegra", "CompraMensal", "CompraOrigem", "DevolucaoMensal", "Documento", "Empresa", "FolhaMensal",
    "GrupoDespesa", "HistoricoStatus", "ImportacaoEmpresa", "ImportacaoNfe", "ItemDespesa", "Levantamento",
    "LevantamentoGrupo", "LevantamentoItem", "MemoriaCalculo", "NcmRegra", "NotaFiscal", "NotaItem",
    "OportunidadeRegistro", "OutraDespesa", "ParametroTributario", "PesoProgresso", "Planejamento",
    "PremissaPlanejamento", "ReformaCronograma", "RelatorioPdf", "SimplesFaixa", "Simulacao",
    "SimulacaoResultado", "TipoDocumento", "Usuario",
]
