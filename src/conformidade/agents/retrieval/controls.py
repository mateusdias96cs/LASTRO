"""Documentos canônicos dos controles.

São o texto que **nós** escrevemos por controle, em português, sempre devolvido
junto com a recuperação — a "âncora determinística" do desenho.

Por que existe: a busca no corpus oficial pode falhar, e falha de um jeito
específico. A medição da Fase 3 mostrou 5 controles em que um distrator sobe ao
topo, todos pares genuinamente ambíguos (token de service account × Secret
comum, raiz somente-leitura × volume somente-leitura). Sem âncora, esse erro de
ranking vira erro de relatório. Com ela, o agente de análise sempre tem a
afirmação normativa correta, e os trechos oficiais entram como respaldo.

Formato: um arquivo por controle em `controls/`, nome = `control_id`. O arquivo
carrega **apenas prosa**. Título, severidade e referências vêm do catálogo de
regras da camada 1 — duplicar metadado aqui só criaria divergência silenciosa.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field

DIRETORIO = Path(__file__).parent / "controls"

SECAO_AFIRMACAO = "Afirmação normativa"
SECAO_PORQUE = "Por que importa"
SECAO_CORRECAO = "Como corrigir"
SECAO_EXCECOES = "Quando não se aplica"

SECOES_OBRIGATORIAS = (SECAO_AFIRMACAO, SECAO_PORQUE, SECAO_CORRECAO)

_CABECALHO = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


class DocumentoCanonico(BaseModel):
    """Texto autoritativo de um controle, escrito por nós."""

    control_id: str
    afirmacao: str
    por_que_importa: str
    como_corrigir: str
    # Vazio é aceitável: nem todo controle tem exceção legítima.
    quando_nao_se_aplica: str = ""
    # Preenchidos a partir do catálogo de regras, não do arquivo.
    titulo: str = ""
    severidade: str = ""
    framework_refs: list[str] = Field(default_factory=list)

    @property
    def texto(self) -> str:
        partes = [
            f"## {SECAO_AFIRMACAO}\n\n{self.afirmacao}",
            f"## {SECAO_PORQUE}\n\n{self.por_que_importa}",
            f"## {SECAO_CORRECAO}\n\n{self.como_corrigir}",
        ]
        if self.quando_nao_se_aplica:
            partes.append(f"## {SECAO_EXCECOES}\n\n{self.quando_nao_se_aplica}")
        return "\n\n".join(partes)


def _dividir_secoes(conteudo: str) -> dict[str, str]:
    marcas = list(_CABECALHO.finditer(conteudo))
    secoes: dict[str, str] = {}
    for i, marca in enumerate(marcas):
        fim = marcas[i + 1].start() if i + 1 < len(marcas) else len(conteudo)
        secoes[marca.group(1).strip()] = conteudo[marca.end() : fim].strip()
    return secoes


def parsear(control_id: str, conteudo: str) -> DocumentoCanonico:
    secoes = _dividir_secoes(conteudo)
    faltando = [s for s in SECOES_OBRIGATORIAS if not secoes.get(s)]
    if faltando:
        raise ValueError(f"{control_id}: seções obrigatórias ausentes ou vazias: {faltando}")
    return DocumentoCanonico(
        control_id=control_id,
        afirmacao=secoes[SECAO_AFIRMACAO],
        por_que_importa=secoes[SECAO_PORQUE],
        como_corrigir=secoes[SECAO_CORRECAO],
        quando_nao_se_aplica=secoes.get(SECAO_EXCECOES, ""),
    )


@lru_cache(maxsize=1)
def carregar_todos(diretorio: Path | None = None) -> dict[str, DocumentoCanonico]:
    """Carrega os documentos e enriquece com os metadados do catálogo."""
    from conformidade.agents.deterministic import list_controls

    base = diretorio or DIRETORIO
    catalogo = {c.control_id: c for c in list_controls()}

    documentos: dict[str, DocumentoCanonico] = {}
    for arquivo in sorted(base.glob("*.md")):
        control_id = arquivo.stem
        doc = parsear(control_id, arquivo.read_text(encoding="utf-8"))
        regra = catalogo.get(control_id)
        if regra is not None:
            doc = doc.model_copy(
                update={
                    "titulo": regra.title,
                    "severidade": regra.severity,
                    "framework_refs": list(regra.framework_refs),
                }
            )
        documentos[control_id] = doc
    return documentos


def documento_de(control_id: str) -> DocumentoCanonico | None:
    return carregar_todos().get(control_id)


def validar(controles_do_catalogo: set[str]) -> list[str]:
    """Inconsistências entre catálogo e documentos. Vazia = íntegro."""
    problemas: list[str] = []
    documentos = carregar_todos()

    faltando = controles_do_catalogo - set(documentos)
    if faltando:
        problemas.append(f"controles sem documento canônico: {sorted(faltando)}")

    orfaos = set(documentos) - controles_do_catalogo
    if orfaos:
        problemas.append(f"documentos sem controle correspondente: {sorted(orfaos)}")

    for control_id, doc in sorted(documentos.items()):
        # 8 e não 12: afirmação normativa boa costuma ser curta, e punir
        # concisão empurraria o texto para o enchimento. O piso existe só para
        # pegar documento escrito pela metade.
        if len(doc.afirmacao.split()) < 8:
            problemas.append(f"{control_id}: afirmação normativa curta demais")
        if len(doc.como_corrigir.split()) < 8:
            problemas.append(f"{control_id}: correção curta demais")

    return problemas
