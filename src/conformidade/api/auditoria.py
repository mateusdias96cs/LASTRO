"""Rota ponta a ponta: o arquivo entra, a configuração corrigida sai.

É a rota que serve o caso de uso real. `/analyze` devolve a estrutura parseada
e os achados, o que interessa a quem integra; aqui devolve o que interessa a
quem só quer o arquivo consertado.

A camada 3 é opcional e a rota não falha sem ela: o arquivo corrigido vem das
camadas 1 e 4, que são determinísticas. Sem Azure configurado, o campo
`com_analise` vem `false` e o relatório diz isso.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from conformidade.pipeline import auditar

router = APIRouter(prefix="/api/v1", tags=["auditoria"])

MAX_UPLOAD_BYTES = 2 * 1024 * 1024


class RespostaAuditoria(BaseModel):
    arquivo: str
    formato: str
    total_de_problemas: int
    corrigidos_automaticamente: list[str] = Field(default_factory=list)
    dependem_de_voce: dict[str, str] = Field(default_factory=dict)
    com_analise: bool = False
    # O que o usuário cola no lugar do original.
    configuracao_corrigida: str = ""
    relatorio_markdown: str = ""


async def _ler(file: UploadFile) -> tuple[str, str]:
    conteudo = await file.read()
    if len(conteudo) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"arquivo acima do limite de {MAX_UPLOAD_BYTES} bytes",
        )
    if not conteudo.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="arquivo vazio"
        )
    try:
        texto = conteudo.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="arquivo não é texto UTF-8",
        ) from exc
    return texto, file.filename or "entrada.yaml"


def _executar(texto: str, nome: str, contexto: str):
    try:
        return auditar(texto, arquivo=nome, contexto=contexto)
    except Exception as exc:  # noqa: BLE001 - arquivo inválido é erro do cliente
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"não foi possível interpretar o arquivo: {exc}",
        ) from exc


@router.post("/auditar", response_model=RespostaAuditoria)
async def post_auditar(
    file: Annotated[UploadFile, File()],
    contexto: Annotated[str, Form()] = "",
) -> RespostaAuditoria:
    """Devolve a configuração corrigida e o relatório.

    `contexto` é opcional e descreve a carga (ex.: "coletor de log em
    DaemonSet"). Ele é **dado**: alimenta a contextualização da camada 3 e não
    influencia nem a detecção nem a verificação.
    """
    texto, nome = await _ler(file)
    resultado = _executar(texto, nome, contexto)
    return RespostaAuditoria(
        arquivo=resultado.arquivo,
        formato=resultado.formato.value,
        total_de_problemas=len(resultado.achados),
        corrigidos_automaticamente=resultado.aplicacao.aplicados,
        dependem_de_voce=resultado.aplicacao.manuais,
        com_analise=resultado.com_analise,
        configuracao_corrigida=resultado.aplicacao.conteudo,
        relatorio_markdown=resultado.markdown,
    )


@router.post("/auditar/configuracao", response_class=PlainTextResponse)
async def post_configuracao(file: Annotated[UploadFile, File()]) -> str:
    """Só o arquivo corrigido, em texto puro.

    Existe para o caso mais direto de todos: `curl ... > compose.yaml`.
    """
    texto, nome = await _ler(file)
    return _executar(texto, nome, "").aplicacao.conteudo
