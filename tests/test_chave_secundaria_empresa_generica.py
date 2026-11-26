"""Dedup secundária (empresa + título) com empresa GENÉRICA.

O bug real, MEDIDO em 26/11 numa única busca no InfoJobs: 41 de 230 vagas
tinham empresa "Confidencial", e "confidencial|analista de dados" saiu para
TRÊS vagas diferentes — Curitiba, Rio de Janeiro e São José dos Pinhais. A
primeira era notificada; as outras duas, descartadas em silêncio por
ja_vista(), que achava a chave que a primeira tinha acabado de gravar. No
jobs.db isso não deixa rastro (a vaga suprimida nunca é gravada), então só
aparece medindo a busca.

Os cards de Curitiba e Rio de Janeiro em tests/fixtures/ são os HTML REAIS
dessa medição, sem edição. O de Fortaleza é o da captura do scraper.
"""

import sqlite3
from pathlib import Path

import pytest

from core.job import Job, calcular_chave_secundaria
from database import database
from scrapers.infojobs import montar_job

FIXTURES = Path(__file__).parent / "fixtures"


def card(nome: str) -> Job:
    return montar_job((FIXTURES / f"infojobs_card_{nome}.html").read_text(encoding="utf-8"))


CURITIBA = "confidencial_curitiba_pr"
RIO = "confidencial_rio_de_janeiro_rj"


def test_os_cards_reais_sao_mesmo_o_caso_do_bug():
    """Guarda do próprio teste: se a captura mudar, o teste perde o sentido."""
    a, b = card(CURITIBA), card(RIO)
    assert a.empresa == b.empresa == "Confidencial"
    assert a.titulo == b.titulo == "Analista De Dados"
    assert a.local != b.local
    assert a.link != b.link


def test_vagas_confidenciais_em_cidades_diferentes_tem_chaves_diferentes():
    assert card(CURITIBA).chave_secundaria != card(RIO).chave_secundaria


def test_mesma_vaga_confidencial_no_mesmo_local_continua_deduplicada():
    """O repost (mesmo título, mesmo local, link novo) ainda é pego —
    'Analista de BI - Trade Marketing' saiu duas vezes em São Paulo na
    mesma medição."""
    original = card(CURITIBA)
    repost = Job(titulo=original.titulo, empresa=original.empresa,
                 local=original.local, link=original.link.replace(".aspx", "-repost.aspx"),
                 site="InfoJobs")
    assert repost.id != original.id
    assert repost.chave_secundaria == original.chave_secundaria


@pytest.mark.parametrize("empresa", [
    "Confidencial", "Empresa Confidencial", "CONFIDENTIAL", "Confidential Company",
    "Não informada", "Nao informado", "Anônimo", "",
])
def test_genericas_viram_o_mesmo_marcador_entre_sites(empresa):
    """"Empresa Confidencial" (LinkedIn) e "Confidencial" (InfoJobs), mesmo
    título e local, ainda são a mesma vaga."""
    assert (calcular_chave_secundaria(empresa, "Analista de Dados", "Fortaleza - CE")
            == calcular_chave_secundaria("Confidencial", "Analista de Dados", "Fortaleza - CE"))


@pytest.mark.parametrize("empresa", ["Capgemini", "La Anónima", "Empresas SB"])
def test_empresa_nomeada_nao_usa_o_local(empresa):
    """Empresa de verdade segue empresa+título: a mesma vaga escrita com local
    diferente em cada site ainda casa. "La Anónima" é uma rede de
    supermercados real, presente no banco — não pode virar genérica."""
    assert (calcular_chave_secundaria(empresa, "Data Analyst", "Fortaleza - CE")
            == calcular_chave_secundaria(empresa, "Data Analyst", "Fortaleza, Ceará, Brasil"))


def test_chave_de_empresa_nomeada_nao_mudou():
    """Compatibilidade com as ~6 mil linhas já gravadas."""
    assert calcular_chave_secundaria("Inetum", "Analista de Dados", "x") == "inetum|analista de dados"


# ------------------------------------------------- ponta a ponta, com banco

@pytest.fixture
def banco(tmp_path, monkeypatch):
    # Pelo MÓDULO, não por valor — ver o comentário em
    # tests/test_guarda_banco_ausente.py sobre o reload de database.
    caminho = tmp_path / "data" / "jobs.db"
    monkeypatch.setattr(database, "DB_PATH", str(caminho))
    monkeypatch.delenv(database.EXIGIR_BANCO_EXISTENTE, raising=False)
    database.iniciar_db()
    return caminho


def test_segunda_confidencial_de_outra_cidade_nao_e_mais_suprimida(banco):
    """O fluxo do ciclo: notifica a primeira, salva, checa a segunda."""
    primeira, segunda = card(CURITIBA), card(RIO)
    assert not database.ja_vista(primeira)
    database.salvar_vaga(primeira, "brasil")
    assert not database.ja_vista(segunda)


def test_backfill_usa_a_mesma_formula(banco):
    """A migração de database.py recalcula a chave de linha antiga. Se ela
    tivesse cópia própria da fórmula, linha velha e vaga nova gerariam
    chaves que nunca casam."""
    vaga = card(CURITIBA)
    with sqlite3.connect(banco) as conexao:
        conexao.execute(
            "INSERT INTO vagas_vistas (id, titulo, empresa, local, site) VALUES (?, ?, ?, ?, ?)",
            ("linha-antiga", vaga.titulo, vaga.empresa, vaga.local, "InfoJobs"),
        )
    database.iniciar_db()
    with sqlite3.connect(banco) as conexao:
        (chave,) = conexao.execute(
            "SELECT chave_secundaria FROM vagas_vistas WHERE id = 'linha-antiga'"
        ).fetchone()
    assert chave == vaga.chave_secundaria
