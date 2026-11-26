"""InfoJobs Brasil — HTML renderizado no servidor, sem navegador.

MEDIDO antes de ligar (26/11, 7 termos, filtro REAL do perfil Brasil,
comparado com o jobs.db de produção), por listagem:

    busca geral   119 únicas →  2 aprovadas (1,7%) → 2 inéditas
    home office    66 únicas →  4 aprovadas (6,1%) → 4 inéditas

As duas listagens rodam, porque cada uma cobre um buraco diferente:

  - A busca geral é quase toda presencial (133 de 177 brutas). As duas
    aprovadas eram PRESENCIAIS EM FORTALEZA — vaga presencial nas
    cidades-alvo é o que o projeto menos acha (o mesmo motivo que segurou a
    Senior).
  - A listagem home office (/vagas-de-emprego-<termo>-trabalho-home-office)
    só tem remoto, que o filtro aceita de qualquer lugar do Brasil. As 62
    rejeitadas ali foram TODAS por cargo ("Analista de Contas a Pagar",
    "Comercial B2B"), nenhuma por local — o filtro fazendo o trabalho dele.

Custo: ~5s pelas duas, sem navegador, contra minutos das fontes Playwright.

PAGINAÇÃO — armadilha medida: `page=2` (minúsculo) é IGNORADO, o site
devolve a página 1 de novo, e `pagina=`/`p=` também. Só `Page=2`, com P
maiúsculo, avança. Sem isso a segunda página repetiria a primeira em
silêncio — a mesma classe de defeito que o projeto já documentou no
emprego.sapo e na randstad. Tem teste cobrando o nome do parâmetro.

Os campos vêm do card da listagem, sem abrir a vaga:
  - título:     <h2 class="... js_vacancyTitle">
  - link:       <a href="/vaga-de-...__ID.aspx">
  - data:       <div hidden class="js_date" data-value="2026/11/25 03:40:00">
                (absoluta, com ano — vira ISO e alimenta Job.publicacao_antiga)
  - local:      primeiro <div class="mb-8"> depois da empresa ("Fortaleza - CE")
  - modalidade: texto logo após o ícone da modalidade ("Presencial",
                "Híbrido", "Home office") — cada uma tem ícone próprio
"""

import html
import re
from urllib.parse import quote_plus

import requests

from core.job import Job
from core.logger import get_logger
from scrapers.base import BaseScraper

logger = get_logger()

URL_BASE = "https://www.infojobs.com.br"
URL_BUSCA = f"{URL_BASE}/empregos.aspx"
URL_HOME_OFFICE = URL_BASE + "/vagas-de-emprego-{termo}-trabalho-home-office.aspx"
PARAM_TERMO = "palabra"
PARAM_PAGINA = "Page"  # P maiúsculo — ver PAGINAÇÃO no docstring do módulo

# 20 vagas por página. Duas páginas por termo é o mesmo alcance da medição.
MAX_PAGINAS = 2
TIMEOUT_SEGUNDOS = 30
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

_SEPARADOR_CARD = "js_rowCard"
_RE_LINK = re.compile(r'href="(/vaga-de-[^"]+)"')
_RE_TITULO = re.compile(r'js_vacancyTitle">(.*?)</h2>', re.S)
# O nome da empresa vem PARTIDO: a última palavra fica num <span
# class="text-nowrap"> à parte ("Gi" + <span>Group</span>), seguida do selo
# de verificação, cujo tooltip carrega HTML próprio. Por isso lê o bloco
# inteiro e corta no selo, em vez de pegar só o <span>.
_RE_EMPRESA = re.compile(r'<div class="text-body">(.*?)(?:<span onclick|</div>)', re.S)
_RE_LOCAL = re.compile(r'<div class="mb-8">\s*(.*?)<', re.S)
# Um ícone por modalidade (medido): #buildings = Presencial,
# #house-and-building = Híbrido, #user-home = Home office.
_RE_MODALIDADE = re.compile(
    r'#(?:buildings|house-and-building|user-home)"\s*/>\s*</svg>\s*(.*?)\s*</div>', re.S
)
_RE_DATA = re.compile(r'js_date" data-value="(\d{4})/(\d{2})/(\d{2})')


def _limpar(texto: str) -> str:
    sem_tags = re.sub(r"<[^>]+>", " ", texto or "")
    return re.sub(r"\s+", " ", html.unescape(sem_tags)).strip()


def _empresa(bloco: str) -> str:
    """Empresa confidencial aparece como "Empresa confidencial" — o rótulo
    "Empresa" é texto solto antes do <span>. Fica só "Confidencial"."""
    nome = _limpar(bloco)
    if nome.lower().startswith("empresa "):
        nome = nome[len("empresa "):]
    return nome.strip().capitalize() if nome.lower() == "confidencial" else (nome or "Não informada")


def _modalidade(texto: str) -> str:
    """Traduz para o vocabulário de Job.modalidade. "" quando desconhecido —
    melhor vazio que errado (ver _confirma_remoto em core/job.py)."""
    t = _limpar(texto).lower()
    if "home office" in t or "remoto" in t:
        return "Remoto"
    if "híbrido" in t or "hibrido" in t:
        return "Híbrido"
    if "presencial" in t:
        return "Presencial"
    return ""


def montar_job(card: str) -> Job | None:
    """Converte o HTML de UM card (o trecho depois de `js_rowCard`) num Job.
    None quando falta link ou título.

    Separada da rede pra ser testada com o HTML real capturado."""
    link = _RE_LINK.search(card or "")
    titulo = _RE_TITULO.search(card or "")
    if not link or not titulo:
        return None

    titulo_limpo = _limpar(titulo.group(1))
    if not titulo_limpo:
        return None

    # A empresa e o local vêm DEPOIS do título no card; procurar a partir
    # dele evita casar um <span class="text-nowrap"> de tag ("NOVA") que
    # aparece antes.
    resto = card[titulo.end():]
    empresa = _RE_EMPRESA.search(resto)
    local = _RE_LOCAL.search(resto)
    modalidade = _RE_MODALIDADE.search(resto)
    data = _RE_DATA.search(card)

    return Job(
        titulo=titulo_limpo,
        empresa=_empresa(empresa.group(1) if empresa else ""),
        local=(_limpar(local.group(1)) if local else "") or "Não informado",
        link=URL_BASE + link.group(1),
        site="InfoJobs",
        publicado_em="-".join(data.groups()) if data else "",
        modalidade=_modalidade(modalidade.group(1)) if modalidade else "",
    )


def _listagens(termo: str) -> list[tuple[str, str, dict]]:
    """As duas listagens consultadas por termo: (rótulo, url, params).
    Ver MEDIDO no docstring do módulo pro porquê das duas."""
    return [
        ("geral", URL_BUSCA, {PARAM_TERMO: termo}),
        ("home office", URL_HOME_OFFICE.format(termo=quote_plus(termo.strip())), {}),
    ]


def extrair_jobs(pagina_html: str) -> list[Job]:
    jobs = []
    for card in (pagina_html or "").split(_SEPARADOR_CARD)[1:]:
        job = montar_job(card)
        if job is not None:
            jobs.append(job)
    return jobs


class InfoJobsScraper(BaseScraper):

    def __init__(self, termos_busca: list[str]):
        self.termos_busca = termos_busca

    def buscar_vagas(self) -> list[Job]:
        vagas: list[Job] = []
        for termo in self.termos_busca:
            vagas.extend(self._buscar_termo(termo))
        logger.info(f"[InfoJobs] {len(vagas)} vaga(s) encontrada(s) no total")
        return vagas

    def _buscar_termo(self, termo: str) -> list[Job]:
        logger.info(f"[InfoJobs] Buscando: {termo}")
        links_vistos: set[str] = set()
        encontradas: list[Job] = []
        for rotulo, url, params in _listagens(termo):
            encontradas.extend(self._paginar(termo, rotulo, url, params, links_vistos))
        return encontradas

    def _paginar(self, termo, rotulo, url, params, links_vistos) -> list[Job]:
        encontradas: list[Job] = []
        for pagina in range(1, MAX_PAGINAS + 1):
            try:
                pagina_html = self._consultar(url, params, pagina)
            except requests.HTTPError as e:
                status = e.response.status_code if e.response is not None else "?"
                logger.warning(
                    f"[InfoJobs] HTTP {status} na página {pagina} de '{termo}' ({rotulo}) — "
                    "parando de paginar."
                )
                break
            except requests.RequestException as e:
                # Sem str(e): a mensagem do requests carrega a URL.
                logger.warning(
                    f"[InfoJobs] {type(e).__name__} na página {pagina} de '{termo}' ({rotulo}) — "
                    "parando de paginar."
                )
                break

            novos = [j for j in extrair_jobs(pagina_html) if j.link not in links_vistos]
            # Página que só repete o que já veio = fim da lista (ou o site
            # voltou a ignorar o parâmetro de página). Para em vez de contar
            # duplicata como vaga. Também descarta a vaga que aparece nas
            # DUAS listagens do mesmo termo.
            if not novos:
                break
            links_vistos.update(j.link for j in novos)
            encontradas.extend(novos)
        return encontradas

    def _consultar(self, url: str, params: dict, pagina: int) -> str:
        params = dict(params)
        if pagina > 1:
            params[PARAM_PAGINA] = pagina
        resposta = requests.get(
            url, params=params, headers={"User-Agent": UA}, timeout=TIMEOUT_SEGUNDOS
        )
        resposta.raise_for_status()
        return resposta.text
