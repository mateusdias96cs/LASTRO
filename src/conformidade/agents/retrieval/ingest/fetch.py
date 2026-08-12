"""Coleta das fontes, com cache em disco.

A rede fica isolada aqui, num único módulo, por dois motivos: os testes de
extração e fatiamento rodam offline, e a reingestão a partir do cache produz
exatamente o mesmo resultado — o que é pré-requisito para a reprodutibilidade
que o projeto sustenta desde a camada 1.
"""

from __future__ import annotations

import hashlib
import urllib.request
from pathlib import Path

from pydantic import BaseModel

USER_AGENT = "conformidade-ingest/1.0 (+auditoria de conformidade; uso interno)"
TIMEOUT = 60


class Origem(BaseModel):
    page_id: str
    url: str
    caminho: str
    sha256: str
    bytes: int
    do_cache: bool


def nome_de_cache(url: str) -> str:
    """Nome de arquivo derivado da URL, estável entre execuções."""
    limpo = url.replace("https://", "").replace("http://", "").replace("/", "_").rstrip("_")
    sufixo = ".pdf" if limpo.lower().endswith(".pdf") else ".html"
    base = limpo[:-4] if limpo.lower().endswith(".pdf") else limpo
    # Trunca nomes muito longos, mantendo unicidade pelo hash da URL completa.
    if len(base) > 120:
        base = base[:110] + "-" + hashlib.sha256(url.encode()).hexdigest()[:8]
    return f"{base}{sufixo}"


def obter(
    page_id: str,
    url: str,
    cache: Path,
    baixar: bool = False,
    arquivo: str | None = None,
) -> Origem | None:
    """Devolve a origem a partir do cache, baixando só se pedido.

    `None` quando o arquivo não está em cache e o download não foi autorizado —
    o pipeline segue com as demais páginas em vez de abortar.

    `arquivo` nomeia o arquivo no cache diretamente, para fonte que não se
    obtém por URL. O CIS Benchmark é assim: o PDF fica atrás de um formulário
    de cadastro, então o download é manual e a URL do manifesto serve só como
    referência de citação no relatório. Derivar o nome da URL, como fazemos
    com as demais fontes, apontaria para um arquivo que nunca existirá.
    """
    cache.mkdir(parents=True, exist_ok=True)
    destino = cache / (arquivo or nome_de_cache(url))

    # Fonte de download manual não é baixável: se não está no cache, está
    # ausente, e forçar o download produziria a página HTML do formulário.
    if arquivo is not None and not destino.exists():
        return None

    if not destino.exists():
        if not baixar:
            return None
        requisicao = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(requisicao, timeout=TIMEOUT) as resposta:  # noqa: S310
            destino.write_bytes(resposta.read())
        do_cache = False
    else:
        do_cache = True

    dados = destino.read_bytes()
    return Origem(
        page_id=page_id,
        url=url,
        caminho=str(destino),
        sha256=hashlib.sha256(dados).hexdigest(),
        bytes=len(dados),
        do_cache=do_cache,
    )
