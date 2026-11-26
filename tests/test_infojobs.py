"""Testes do scraper do InfoJobs, contra o HTML REAL capturado do site.

Os três cards em tests/fixtures/infojobs_card_*.html foram copiados da
listagem de verdade (26/11), sem edição:

  fortaleza   busca geral "analista de dados", Page=2 — presencial em
              Fortaleza, a vaga que justificou ligar a fonte
  homeoffice  listagem /vagas-de-emprego-analista+de+dados-trabalho-home-office
  hibrido     busca geral "power bi" — único card híbrido da página

Regras do projeto: o dado de teste é capturado, não inventado (ver README,
o caso da Sólides). Os bugs que estes testes cobram foram todos achados na
medição, não imaginados:

  - `page=2` minúsculo é ignorado pelo site (devolve a página 1 de novo);
  - a empresa vem partida em dois nós ("Gi" + <span>Group</span>);
  - cada modalidade tem ícone próprio — ler só #buildings deixava 44 de 177
    vagas sem modalidade, inclusive TODAS as remotas.
"""

from pathlib import Path

import pytest

from core.perfis import PERFIL_BR
from scrapers import infojobs
from scrapers.infojobs import PARAM_PAGINA, _listagens, extrair_jobs, montar_job

FIXTURES = Path(__file__).parent / "fixtures"


def card(nome: str) -> str:
    return (FIXTURES / f"infojobs_card_{nome}.html").read_text(encoding="utf-8")


def test_card_real_presencial_em_fortaleza():
    job = montar_job(card("fortaleza"))
    assert job.titulo == "[SOLYS GESTÃO ADMINISTRATIVA] Analista De Dados"
    assert job.empresa == "Confidencial"
    assert job.local == "Fortaleza - CE"
    assert job.modalidade == "Presencial"
    assert job.publicado_em == "2026-11-20"
    assert job.link == (
        "https://www.infojobs.com.br/"
        "vaga-de-solys-gestao-administrativa-analista-dados-em-ceara__12238442.aspx"
    )
    assert job.site == "InfoJobs"


def test_presencial_em_fortaleza_passa_no_filtro():
    assert montar_job(card("fortaleza")).combina_com(PERFIL_BR.regras)


def test_card_real_home_office():
    job = montar_job(card("homeoffice"))
    assert job.titulo == "Analista De Dados Sênior | CLT | Todo O Brasil"
    assert job.empresa == "King of Languages"
    assert job.local == "Todo Brasil"
    assert job.modalidade == "Remoto"
    assert job.publicado_em == "2026-11-18"


def test_home_office_passa_no_filtro():
    assert montar_job(card("homeoffice")).combina_com(PERFIL_BR.regras)


def test_card_real_hibrido_e_empresa_partida_em_dois_nos():
    job = montar_job(card("hibrido"))
    assert job.empresa == "Gi Group"  # não só "Group"
    assert job.modalidade == "Híbrido"
    assert job.local == "Rio de Janeiro - RJ"


def test_extrai_todos_os_cards_de_uma_pagina():
    pagina = "".join(f"<div class='x js_rowCard'>{card(n)}" for n in ("fortaleza", "homeoffice", "hibrido"))
    assert len(extrair_jobs("<html>cabeçalho" + pagina)) == 3


@pytest.mark.parametrize("quebra", ["js_vacancyTitle", 'href="/vaga-de-'])
def test_card_sem_titulo_ou_link_e_descartado(quebra):
    assert montar_job(card("fortaleza").replace(quebra, "removido")) is None


def test_parametro_de_pagina_e_com_p_maiusculo():
    """`page=2` é ignorado pelo site (medido) — a página 2 repetiria a 1."""
    assert PARAM_PAGINA == "Page"


def test_consulta_as_duas_listagens_com_termo_acentuado():
    (_, url_geral, params_geral), (_, url_ho, params_ho) = _listagens("analista de inteligência")
    assert url_geral.endswith("/empregos.aspx")
    assert params_geral == {"palabra": "analista de inteligência"}
    assert url_ho == (
        "https://www.infojobs.com.br/vagas-de-emprego-"
        "analista+de+intelig%C3%AAncia-trabalho-home-office.aspx"
    )
    assert params_ho == {}


class _Resposta:
    def __init__(self, texto):
        self.text = texto

    def raise_for_status(self):
        pass


def _pagina(*nomes):
    return "".join(f"<div class='js_rowCard'>{card(n)}" for n in nomes)


def test_pagina_repetida_encerra_a_paginacao_sem_duplicar(monkeypatch):
    """Se o site voltar a ignorar o parâmetro de página, a página 2 vem igual
    à 1: tem que parar, não somar duplicata."""
    chamadas = []

    def falso_get(url, params, headers, timeout):
        chamadas.append((url, params.get(PARAM_PAGINA)))
        return _Resposta(_pagina("fortaleza"))

    monkeypatch.setattr(infojobs.requests, "get", falso_get)
    vagas = infojobs.InfoJobsScraper(["analista de dados"]).buscar_vagas()
    assert len(vagas) == 1  # a mesma vaga nas duas listagens conta uma vez
    # geral: pág. 1 e 2 (repetida, para); home office: pág. 1 (repetida, para)
    assert [p for _, p in chamadas] == [None, 2, None]


def test_pagina_2_usa_o_parametro_certo(monkeypatch):
    paginas = iter([_pagina("fortaleza"), _pagina("hibrido"), "", ""])
    vistos = []

    def falso_get(url, params, headers, timeout):
        vistos.append(dict(params))
        return _Resposta(next(paginas))

    monkeypatch.setattr(infojobs.requests, "get", falso_get)
    vagas = infojobs.InfoJobsScraper(["power bi"]).buscar_vagas()
    assert len(vagas) == 2
    assert vistos[1] == {"palabra": "power bi", "Page": 2}


def test_erro_de_rede_nao_derruba_o_scraper(monkeypatch):
    def falha(*a, **k):
        raise infojobs.requests.ConnectionError("sem rede")

    monkeypatch.setattr(infojobs.requests, "get", falha)
    assert infojobs.InfoJobsScraper(["dados"]).buscar_vagas() == []
