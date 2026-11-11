"""Importa todos os modelos para registrá-los no metadata (Alembic e create_all)."""
from .auditoria import AuditoriaCheckpoint, EventoAuditoria
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
from .planejamento import HistoricoStatus, Planejamento, PremissaPlanejamento, RevisaoProduto
from .simulacao import MemoriaCalculo, OportunidadeRegistro, RelatorioPdf, Simulacao, SimulacaoResultado
from .tabelas import (AliquotaUf, CfopRegra, MarcaImplantacao, NcmRegra, Norma, ParametroTributario, ReformaCronograma, ReformaHistorico, RegraReforma, RegraSt,
                      SimplesFaixa)

__all__ = [
    "AliquotaUf", "AuditoriaCheckpoint", "EventoAuditoria", "Bem", "CfopRegra", "CompraMensal", "CompraOrigem", "DevolucaoMensal", "Documento", "Empresa", "FolhaMensal",
    "GrupoDespesa", "HistoricoStatus", "ImportacaoEmpresa", "ImportacaoNfe", "ItemDespesa", "Levantamento",
    "LevantamentoGrupo", "LevantamentoItem", "MarcaImplantacao", "MemoriaCalculo", "NcmRegra", "NotaFiscal", "NotaItem",
    "OportunidadeRegistro", "OutraDespesa", "ParametroTributario", "PesoProgresso", "Planejamento",
    "Norma", "PremissaPlanejamento", "ReformaCronograma", "ReformaHistorico", "RegraReforma", "RegraSt", "RelatorioPdf", "RevisaoProduto", "SimplesFaixa", "Simulacao",
    "SimulacaoResultado", "TipoDocumento", "Usuario",
]
