"""Remotar — agregador brasileiro de vagas remotas, busca por API, sem navegador.

MEDIDO antes de ligar (26/11, 7 termos × 2 páginas, filtro REAL do perfil
Brasil, comparado com o jobs.db de produção):

    531 vagas únicas → 123 aprovadas (23,2%) → 103 inéditas no banco, em 5s.

É o maior rendimento do projeto — o LinkedIn, a melhor fonte até aqui, fica
em ~8,5%. A razão é estrutural: o Remotar só publica vaga remota ou híbrida,
e remoto é exatamente o que o filtro aceita fora das cidades-alvo.

As inéditas não são ilusão de deduplicação: 98 das 103 eram de novembro, e
os links apontam para ATSs que nenhuma outra fonte cobre (InHire, Quickin,
Lever, Greenhouse, página própria da empresa). O Remotar agrega; o link
final é o da candidatura de verdade (`externalLink`).

Mesmo formato da Senior: JSON com campos separados (`type`, `city`,
`state`), então não há texto solto de localização pra adivinhar.
"""

import requests

from core.job import Job
from core.logger import get_logger
from scrapers.base import BaseScraper

logger = get_logger()

URL_BUSCA = "https://api.remotar.com.br/jobs"
# Página pública da vaga no próprio Remotar. Confirmado ao vivo (HTTP 200).
# Só é usada quando a vaga não traz `externalLink` — nas 50 capturadas na
# medição, todas traziam.
URL_VAGA = "https://remotar.com.br/job/"

# A API devolve 50 por página, ordenadas da mais nova pra mais antiga. Duas
# páginas = 100 vagas por termo, o que cobre bem mais que 3h de publicação.
MAX_PAGINAS = 2
TIMEOUT_SEGUNDOS = 30

_MODALIDADE = {
    "remote": "Remoto",
    "hybrid": "Híbrido",
    "onsite": "Presencial",
    "presential": "Presencial",
}


def _local(item: dict) -> str:
    """"São Paulo - SP" quando a vaga declara cidade; "Remoto" quando é
    remota sem cidade (o caso mais comum). Vaga híbrida SEM cidade fica
    "Não informado" de propósito: chamar de "Remoto" faria o filtro aprovar
    vaga que exige presença em algum lugar."""
    cidade = (item.get("city") or "").strip()
    uf = (item.get("state") or "").strip()
    partes = " - ".join(p for p in (cidade, uf) if p)
    if partes:
        return partes
    if (item.get("type") or "") == "remote":
        return "Remoto"
    return "Não informado"


def _empresa(item: dict) -> str:
    nome = (item.get("company") or {}).get("name") or item.get("companyDisplayName") or ""
    return nome.strip() or "Não informada"


def montar_job(item: dict) -> Job | None:
    """Converte um item de `data` num Job. None quando a vaga não serve (sem
    id/título, inativa ou expirada).

    Separada da chamada de rede pra ser testada com o JSON real capturado."""
    item = item or {}
    id_vaga = item.get("id")
    titulo = (item.get("title") or "").strip()
    if not id_vaga or not titulo:
        return None
    if item.get("expired") or item.get("active") is False:
        return None

    tipo = (item.get("type") or "").lower()
    return Job(
        titulo=titulo,
        empresa=_empresa(item),
        local=_local(item),
        link=(item.get("externalLink") or "").strip() or f"{URL_VAGA}{id_vaga}",
        site="Remotar",
        publicado_em=str(item.get("createdAt") or "")[:10],
        modalidade=_MODALIDADE.get(tipo, ""),
    )


class RemotarScraper(BaseScraper):

    def __init__(self, termos_busca: list[str]):
        self.termos_busca = termos_busca

    def buscar_vagas(self) -> list[Job]:
        vagas: list[Job] = []
        for termo in self.termos_busca:
            vagas.extend(self._buscar_termo(termo))
        logger.info(f"[Remotar] {len(vagas)} vaga(s) encontrada(s) no total")
        return vagas

    def _buscar_termo(self, termo: str) -> list[Job]:
        logger.info(f"[Remotar] Buscando: {termo}")
        encontradas: list[Job] = []

        for pagina in range(1, MAX_PAGINAS + 1):
            try:
                dados = self._consultar(termo, pagina)
            except requests.HTTPError as e:
                status = e.response.status_code if e.response is not None else "?"
                logger.warning(
                    f"[Remotar] HTTP {status} na página {pagina} de '{termo}' — parando de paginar."
                )
                break
            except (requests.RequestException, ValueError) as e:
                # Sem str(e): a mensagem do requests carrega a URL (mesmo
                # hábito da Senior e do notifier).
                logger.warning(
                    f"[Remotar] {type(e).__name__} na página {pagina} de '{termo}' — parando de paginar."
                )
                break

            itens = dados.get("data") or []
            for item in itens:
                job = montar_job(item)
                if job is not None:
                    encontradas.append(job)

            ultima = int((dados.get("meta") or {}).get("last_page") or 0)
            if not itens or pagina >= ultima:
                break

        return encontradas

    def _consultar(self, termo: str, pagina: int) -> dict:
        resposta = requests.get(
            URL_BUSCA,
            params={"search": termo, "page": pagina},
            timeout=TIMEOUT_SEGUNDOS,
        )
        resposta.raise_for_status()
        return resposta.json()
