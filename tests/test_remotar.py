"""Testes do scraper do Remotar, contra o JSON REAL capturado da API.

Os itens abaixo foram copiados da resposta de verdade de
api.remotar.com.br/jobs?search=analista%20de%20bi (26/11), só com os campos
que o scraper lê — `description`, `jobBenefits` etc. foram cortados por
tamanho, não editados.

O risco que motivou estes testes: o Remotar publica vaga REMOTA e HÍBRIDA
na mesma lista. Se a híbrida sem cidade virasse local "Remoto", o filtro a
aprovaria como remota — notificando vaga que exige presença em algum lugar.
"""

import copy

import pytest

from core.perfis import PERFIL_BR
from scrapers import remotar
from scrapers.remotar import URL_VAGA, montar_job

ITEM_REMOTO = {
    "id": 173055,
    "title": "Analista de BI Sênior (Foco em Riscos)",
    "city": None,
    "state": None,
    "country": None,
    "type": "remote",
    "externalLink": "https://unicredbr.gupy.io/job/eyJqb2JJZCI6MTI4Nzk3NjQsInNvdXJjZSI6InJlbW90YXIifQ==?jobBoardSource=remotar",
    "isExternalLink": True,
    "expired": False,
    "active": True,
    "createdAt": "2026-11-23T16:05:58.091-03:00",
    "companyDisplayName": None,
    "company": {"id": 165, "name": "UNICRED"},
}

ITEM_HIBRIDO = {
    "id": 173393,
    "title": "Analista de Dados Pleno (Foco em IA )",
    "city": "São Paulo",
    "state": "SP",
    "country": None,
    "type": "hybrid",
    "externalLink": "https://mazzatech.inhire.app/vagas/247cd5af-e14a-43d7-b989-c3ea7b60febd/analista-de-dados-pleno-foco-em-ia",
    "isExternalLink": True,
    "expired": False,
    "active": True,
    "createdAt": "2026-11-24T19:32:20.720-03:00",
    "companyDisplayName": None,
    "company": {"id": 8161, "name": "mazzatech"},
}


def item(base, **mudancas):
    novo = copy.deepcopy(base)
    novo.update(mudancas)
    return novo


def test_converte_vaga_remota_real():
    job = montar_job(ITEM_REMOTO)
    assert job.titulo == "Analista de BI Sênior (Foco em Riscos)"
    assert job.empresa == "UNICRED"
    assert job.local == "Remoto"
    assert job.modalidade == "Remoto"
    assert job.publicado_em == "2026-11-23"
    assert job.site == "Remotar"
    # O link é o da candidatura de verdade (o ATS), não a página do Remotar.
    assert job.link.startswith("https://unicredbr.gupy.io/job/")


def test_vaga_remota_real_passa_no_filtro_do_perfil_brasil():
    assert montar_job(ITEM_REMOTO).combina_com(PERFIL_BR.regras)


def test_converte_vaga_hibrida_real_com_cidade():
    job = montar_job(ITEM_HIBRIDO)
    assert job.local == "São Paulo - SP"
    assert job.modalidade == "Híbrido"


def test_hibrida_em_sao_paulo_nao_passa_no_filtro():
    """São Paulo não está nas cidades-alvo e a vaga não é remota."""
    assert not montar_job(ITEM_HIBRIDO).combina_com(PERFIL_BR.regras)


def test_hibrida_sem_cidade_nao_vira_remota():
    """O bug que o teste existe pra impedir: 9 das 50 vagas capturadas
    vinham com city/state vazios. Híbrida sem cidade NÃO pode virar
    "Remoto"."""
    job = montar_job(item(ITEM_HIBRIDO, city="", state=""))
    assert job.local == "Não informado"
    assert job.modalidade == "Híbrido"
    assert not job.combina_com(PERFIL_BR.regras)


def test_sem_link_externo_usa_pagina_do_remotar():
    job = montar_job(item(ITEM_REMOTO, externalLink=None, isExternalLink=False))
    assert job.link == f"{URL_VAGA}173055"


def test_empresa_pelo_nome_de_exibicao_quando_nao_ha_company():
    job = montar_job(item(ITEM_REMOTO, company=None, companyDisplayName="Acme"))
    assert job.empresa == "Acme"


@pytest.mark.parametrize("mudanca", [
    {"expired": True},
    {"active": False},
    {"title": ""},
    {"id": None},
])
def test_descarta_vaga_que_nao_serve(mudanca):
    assert montar_job(item(ITEM_REMOTO, **mudanca)) is None


class _Resposta:
    def __init__(self, dados):
        self._dados = dados

    def raise_for_status(self):
        pass

    def json(self):
        return self._dados


def test_pagina_ate_o_limite_e_respeita_last_page(monkeypatch):
    chamadas = []

    def falso_get(url, params, timeout):
        chamadas.append(params["page"])
        return _Resposta({
            "meta": {"last_page": 33},
            "data": [item(ITEM_REMOTO, id=params["page"] * 1000)],
        })

    monkeypatch.setattr(remotar.requests, "get", falso_get)
    vagas = remotar.RemotarScraper(["dados"]).buscar_vagas()
    assert chamadas == list(range(1, remotar.MAX_PAGINAS + 1))
    assert len(vagas) == remotar.MAX_PAGINAS


def test_para_na_ultima_pagina_informada(monkeypatch):
    chamadas = []

    def falso_get(url, params, timeout):
        chamadas.append(params["page"])
        return _Resposta({"meta": {"last_page": 1}, "data": [ITEM_REMOTO]})

    monkeypatch.setattr(remotar.requests, "get", falso_get)
    remotar.RemotarScraper(["dados"]).buscar_vagas()
    assert chamadas == [1]


def test_erro_de_rede_nao_derruba_o_scraper(monkeypatch):
    def falha(*a, **k):
        raise remotar.requests.ConnectionError("sem rede")

    monkeypatch.setattr(remotar.requests, "get", falha)
    assert remotar.RemotarScraper(["dados", "bi"]).buscar_vagas() == []
