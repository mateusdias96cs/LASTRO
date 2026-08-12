"""Extração de seções a partir de HTML e PDF.

Usa `html.parser` da biblioteca padrão em vez de uma dependência de scraping.
Não é purismo: o que precisamos é justamente o que um extrator genérico de
texto **perde** — a hierarquia de títulos. `heading_path` vira parte do texto
do chunk e é o que dá contexto a um trecho recuperado isoladamente.

O segundo motivo é ruído. Extrair texto com regex sobre a página inteira traz
menu de navegação, rodapé e barra lateral, que em site de documentação repetem
os mesmos termos em todas as páginas e envenenam a busca lexical.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

from pydantic import BaseModel

# Elementos cujo conteúdo nunca é texto do documento.
IGNORADOS = frozenset(
    {
        "script",
        "style",
        "nav",
        "header",
        "footer",
        "aside",
        "svg",
        "button",
        "form",
        "noscript",
        "iframe",
        "select",
        "template",
    }
)
TITULOS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}
# Elementos que encerram um parágrafo de texto.
BLOCOS = frozenset(
    {"p", "li", "td", "th", "pre", "div", "section", "article", "blockquote", "dd", "dt"}
)


class Secao(BaseModel):
    """Trecho de documento sob um mesmo título."""

    heading_path: str
    nivel: int
    ordem: int
    texto: str


class _ExtratorHTML(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.secoes: list[Secao] = []
        self._pilha: list[tuple[int, str]] = []  # (nível, título)
        self._ignorar = 0
        self._titulo_atual: int | None = None
        self._buffer_titulo: list[str] = []
        self._buffer_texto: list[str] = []
        self._ordem = 0

    # -- ciclo de vida das seções ------------------------------------------

    def _fechar_secao(self) -> None:
        texto = " ".join(t.strip() for t in self._buffer_texto if t.strip())
        texto = re.sub(r"\s+", " ", texto).strip()
        self._buffer_texto = []
        if not texto:
            return
        self.secoes.append(
            Secao(
                heading_path=" > ".join(t for _, t in self._pilha) or "(início)",
                nivel=self._pilha[-1][0] if self._pilha else 0,
                ordem=self._ordem,
                texto=texto,
            )
        )
        self._ordem += 1

    def _empilhar(self, nivel: int, titulo: str) -> None:
        while self._pilha and self._pilha[-1][0] >= nivel:
            self._pilha.pop()
        self._pilha.append((nivel, titulo))

    # -- callbacks do parser -----------------------------------------------

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in IGNORADOS:
            self._ignorar += 1
            return
        if self._ignorar:
            return
        if tag in TITULOS:
            self._fechar_secao()
            self._titulo_atual = TITULOS[tag]
            self._buffer_titulo = []
        elif tag in ("br", "hr"):
            self._buffer_texto.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in IGNORADOS:
            self._ignorar = max(0, self._ignorar - 1)
            return
        if self._ignorar:
            return
        if tag in TITULOS and self._titulo_atual is not None:
            titulo = re.sub(r"\s+", " ", "".join(self._buffer_titulo)).strip()
            # Sites de documentação anexam "#" de âncora ao título.
            titulo = titulo.rstrip("#").strip()
            if titulo:
                self._empilhar(self._titulo_atual, titulo)
            self._titulo_atual = None
            self._buffer_titulo = []
        elif tag in BLOCOS:
            self._buffer_texto.append(" ")

    def handle_data(self, data: str) -> None:
        if self._ignorar:
            return
        if self._titulo_atual is not None:
            self._buffer_titulo.append(data)
        else:
            self._buffer_texto.append(data)

    def close(self) -> None:  # type: ignore[override]
        super().close()
        self._fechar_secao()


def extrair_html(conteudo: str) -> list[Secao]:
    parser = _ExtratorHTML()
    parser.feed(conteudo)
    parser.close()
    return parser.secoes


# --------------------------------------------------------------------------
# PDF
# --------------------------------------------------------------------------

# Títulos numerados do NIST: "3.1.1 Image vulnerabilities".
_TITULO_NUMERADO = re.compile(r"^(\d+(?:\.\d+){0,3})\s+([A-Z][^\n]{3,80})$")


# --------------------------------------------------------------------------
# CIS Benchmark
# --------------------------------------------------------------------------

# Seções do CIS Docker Benchmark que descrevem o que o usuário nos envia.
#
# O documento tem 114 recomendações, e 70 delas são sobre a máquina host e o
# daemon: partição separada para `/var/lib/docker`, dono do `docker.service`,
# flags do `dockerd`, Swarm. Nada disso aparece num Dockerfile, num compose ou
# num manifesto — que é a única entrada que este sistema recebe.
#
# Ingerir as 114 adicionaria 70 documentos de alta densidade normativa e
# vocabulário quase idêntico (`Ensure that ... is set to ...`) ao lado dos 44
# que importam. A auditoria da camada 2 já mostrou o custo disso: corpus maior
# não é corpus melhor, e vizinho plausível é a pior falha desta camada.
SECOES_NO_ESCOPO = {
    "4": "Container Images and Build File Configuration",
    "5": "Container Runtime Configuration",
}

# Blocos mantidos, em ordem. `Audit` fica de fora de propósito: são comandos
# `docker inspect` contra container em execução, e nós lemos arquivo de
# configuração — o texto seria ruído longo e não citável. `Default Value`,
# `References` e `CIS Controls` são referência cruzada, não norma.
BLOCOS_CIS = ("Description", "Rationale", "Impact", "Remediation")

_REC_CIS = re.compile(
    r"(?P<num>\d+\.\d+(?:\.\d+)?)\s+"
    r"(?P<titulo>Ensure[^\n]{5,120}?)\s*"
    r"\((?:Automated|Manual)\)\s+"
    # A âncora que separa o corpo do sumário: só o corpo traz este rótulo.
    r"Profile Applicability:"
)
_RODAPE_CIS = re.compile(r"Page \d+\s*Internal Only\s*-\s*General\s*", re.I)
_ROTULO_CIS = re.compile(
    r"\b(Description|Rationale|Impact|Audit|Remediation|Default Value|References|"
    r"CIS Controls|Additional Information):\s*"
)


def extrair_cis(caminho: str) -> list[Secao]:
    """Extrai uma seção por recomendação do CIS Benchmark.

    Diferente de `extrair_pdf`, que procura títulos numerados em prosa: aqui a
    estrutura é regular e nomeada, e vale explorá-la. Cada recomendação vira
    **uma** seção — nome, descrição, justificativa, impacto e remediação —, que
    é a granularidade que o agente de análise precisa para citar.

    É a diferença que o resto do corpus não oferece. A documentação da Docker e
    do Kubernetes é tutorial e referência de sintaxe; o CIS é escrito como
    especificação de configuração, com o bloco `Remediation` dizendo qual é o
    valor correto. Isso é o que o sistema precisa devolver ao usuário.
    """
    from pypdf import PdfReader

    reader = PdfReader(caminho)
    bruto = "\n".join((pagina.extract_text() or "") for pagina in reader.pages)
    bruto = _RODAPE_CIS.sub(" ", bruto)

    ocorrencias = list(_REC_CIS.finditer(bruto))
    secoes: list[Secao] = []
    ordem = 0

    for i, m in enumerate(ocorrencias):
        raiz = m.group("num").split(".")[0]
        if raiz not in SECOES_NO_ESCOPO:
            continue

        fim = ocorrencias[i + 1].start() if i + 1 < len(ocorrencias) else len(bruto)
        corpo = bruto[m.end() : fim]

        partes: list[str] = []
        rotulos = list(_ROTULO_CIS.finditer(corpo))
        for j, rot in enumerate(rotulos):
            nome = rot.group(1)
            if nome not in BLOCOS_CIS:
                continue
            ate = rotulos[j + 1].start() if j + 1 < len(rotulos) else len(corpo)
            conteudo = re.sub(r"\s+", " ", corpo[rot.end() : ate]).strip()
            if conteudo:
                partes.append(f"{nome}: {conteudo}")

        if not partes:
            continue

        titulo = re.sub(r"\s+", " ", m.group("titulo")).strip()
        secoes.append(
            Secao(
                heading_path=(
                    f"CIS Docker Benchmark > {SECOES_NO_ESCOPO[raiz]} > {m.group('num')} {titulo}"
                ),
                nivel=2,
                ordem=ordem,
                texto=" ".join(partes),
            )
        )
        ordem += 1

    return secoes


def extrair_pdf(caminho: str) -> list[Secao]:
    """Extrai seções de um PDF com títulos numerados.

    O NIST SP 800-190 usa numeração hierárquica consistente, então o título da
    seção é detectável sem heurística frágil de fonte ou posição.
    """
    from pypdf import PdfReader

    reader = PdfReader(caminho)
    linhas: list[str] = []
    for pagina in reader.pages:
        linhas.extend((pagina.extract_text() or "").splitlines())

    secoes: list[Secao] = []
    pilha: list[tuple[int, str]] = []
    buffer: list[str] = []
    ordem = 0

    def fechar() -> None:
        nonlocal ordem, buffer
        texto = re.sub(r"\s+", " ", " ".join(buffer)).strip()
        buffer = []
        if len(texto) < 40:  # cabeçalho/rodapé solto não vira seção
            return
        secoes.append(
            Secao(
                heading_path=" > ".join(t for _, t in pilha) or "(início)",
                nivel=pilha[-1][0] if pilha else 0,
                ordem=ordem,
                texto=texto,
            )
        )
        ordem += 1

    for linha in linhas:
        limpa = linha.strip()
        m = _TITULO_NUMERADO.match(limpa)
        if m:
            fechar()
            numero, titulo = m.group(1), m.group(2).strip()
            nivel = numero.count(".") + 1
            while pilha and pilha[-1][0] >= nivel:
                pilha.pop()
            pilha.append((nivel, f"{numero} {titulo}"))
        else:
            buffer.append(limpa)

    fechar()
    return secoes
