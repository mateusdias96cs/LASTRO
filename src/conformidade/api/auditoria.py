"""Rota ponta a ponta: o arquivo entra, a configuração corrigida sai.

É a rota que serve o caso de uso real. `/analyze` devolve a estrutura parseada
e os achados, o que interessa a quem integra; aqui devolve o que interessa a
quem só quer o arquivo consertado.

A camada 3 é opcional e a rota não falha sem ela: o arquivo corrigido vem das
camadas 1 e 4, que são determinísticas. Sem Azure configurado, o campo
`com_analise` vem `false` e o relatório diz isso.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field

from conformidade.api.limite import limitar
from conformidade.pipeline import Progresso, auditar, diagnostico

_log = logging.getLogger("conformidade.api")

router = APIRouter(prefix="/api/v1", tags=["auditoria"])

MAX_UPLOAD_BYTES = 2 * 1024 * 1024

# Teto do campo livre que descreve a carga.
#
# Sem teto ele era aceito com 200.000 caracteres, medido. Dois problemas: o
# texto vai junto de CADA achado para o modelo, então o custo em tokens é
# multiplicado pelo número de achados; e um campo livre grande é o veículo
# natural de injeção de prompt. 2.000 é folga larga para a frase que o
# campo pede ("coletor de log em DaemonSet, precisa ler /var/log do nó").
MAX_CONTEXTO_CHARS = 2000


class CitacaoNaResposta(BaseModel):
    trecho: str
    url: str = ""


class AchadoNaResposta(BaseModel):
    """Um achado, no formato que a tela precisa.

    Achatado de propósito. O frontend não deve navegar
    `criticado.analisado.citacoes[].trecho_exato` para mostrar uma citação —
    isso acoplaria a interface à estrutura interna das camadas 3 e 4, e
    qualquer refatoração interna quebraria a tela.
    """

    control_id: str
    titulo: str
    severidade: str
    veredito: str
    explicacao: str
    # Trecho recortado do arquivo enviado. Vai para a tela dentro de bloco de
    # código, nunca como texto corrido — é dado do usuário, não nosso.
    evidencia: str = ""
    onde: str = ""
    citacoes: list[CitacaoNaResposta] = Field(default_factory=list)
    # Preenchido quando não há fonte oficial para o controle. A tela declara a
    # ausência em vez de deixar o espaço vazio, que pareceria descuido.
    aviso_de_respaldo: str = ""
    # O que o verificador automático reparou na análise, se reparou.
    ressalvas: list[str] = Field(default_factory=list)
    # Trecho de configuração e onde encaixar.
    correcao: str = ""
    correcao_caminho: str = ""
    corrigido_automaticamente: bool = False
    # `False` quando a explicação veio do catálogo determinístico em vez da
    # camada 3 — a tela marca quais achados têm contextualização de verdade.
    explicado_por_ia: bool = False


class RespostaAuditoria(BaseModel):
    arquivo: str
    formato: str
    total_de_problemas: int
    corrigidos_automaticamente: list[str] = Field(default_factory=list)
    dependem_de_voce: dict[str, str] = Field(default_factory=dict)
    com_analise: bool = False
    # Quantos achados a camada 3 explicou, de fato. A degradação é parcial: o
    # limite de requisições por minuto do deployment pode derrubar os últimos
    # de um arquivo grande, e a tela precisa poder dizer "3 de 9" em vez de
    # afirmar que a IA participou ou não participou.
    explicados_por_ia: int = 0
    # Por que a camada 3 não participou de tudo. Vazio quando participou.
    motivo_sem_ia: str = ""
    # O que o usuário cola no lugar do original.
    configuracao_corrigida: str = ""
    relatorio_markdown: str = ""
    achados: list[AchadoNaResposta] = Field(default_factory=list)


async def _ler(file: UploadFile) -> tuple[str, str]:
    # Lê um byte além do teto, e não o arquivo inteiro.
    #
    # A versão anterior fazia `await file.read()` e só então media o tamanho:
    # para recusar um corpo grande, primeiro o materializava. Pedir
    # `MAX + 1` basta para saber que estourou, e o que não couber nunca é
    # trazido para a memória.
    conteudo = await file.read(MAX_UPLOAD_BYTES + 1)
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


# O que o cliente vê quando o parse falha. Sempre a mesma frase.
#
# A versão anterior interpolava a exceção, e isso vazava implementação: um
# teste devolveu `maximum recursion depth exceeded`, e antes disso o
# `PermissionError` do cache chegou à tela com o caminho absoluto dentro do
# container. Nada disso ajuda quem enviou o arquivo, e tudo isso ajuda quem
# está sondando. O detalhe continua existindo, no log, onde é útil.
ERRO_DE_PARSE = (
    "não foi possível interpretar o arquivo; confira se é um Dockerfile, "
    "docker-compose ou manifesto do Kubernetes válido"
)


def _executar(texto: str, nome: str, contexto: str):
    try:
        return auditar(texto, arquivo=nome, contexto=contexto)
    except Exception as exc:  # noqa: BLE001 - arquivo inválido é erro do cliente
        _log.warning(
            "falha ao interpretar arquivo enviado",
            extra={"erro": type(exc).__name__, "detalhe": str(exc), "arquivo": nome},
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=ERRO_DE_PARSE,
        ) from exc


_ORDEM_SEVERIDADE = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


def _achados(resultado) -> list[AchadoNaResposta]:
    from conformidade.agents.critic.correcoes import correcao_para
    from conformidade.agents.retrieval.cobertura import AVISO_PADRAO, motivo_da_ausencia

    por_controle = {c.control_id: c for _, c in resultado.criticados}
    aplicados = set(resultado.aplicacao.aplicados)
    saida: list[AchadoNaResposta] = []

    for achado in resultado.achados:
        criticado = por_controle.get(achado.control_id)
        analisado = criticado.analisado if criticado else None
        correcao = correcao_para(achado.control_id, resultado.formato)
        motivo = motivo_da_ausencia(achado.control_id)
        citacoes = [
            CitacaoNaResposta(trecho=c.trecho_exato, url=c.url)
            for c in (analisado.citacoes if analisado else [])
        ]
        saida.append(
            AchadoNaResposta(
                control_id=achado.control_id,
                titulo=achado.title,
                severidade=achado.severity.value,
                veredito=analisado.veredito.value if analisado else "confirmado",
                explicacao=analisado.explicacao if analisado else achado.message,
                evidencia=achado.evidence or "",
                onde=achado.target or "",
                citacoes=citacoes,
                aviso_de_respaldo=(f"{AVISO_PADRAO} {motivo}" if motivo and not citacoes else ""),
                ressalvas=[
                    f"{o.reparo.value}: {o.detalhe}"
                    for o in (criticado.objecoes if criticado else ())
                ],
                correcao=correcao.trecho if correcao else "",
                correcao_caminho=correcao.caminho if correcao else "",
                corrigido_automaticamente=achado.control_id in aplicados,
                explicado_por_ia=bool(citacoes)
                or bool(analisado and analisado.justificativa_do_ajuste),
            )
        )

    saida.sort(key=lambda a: (_ORDEM_SEVERIDADE.get(a.severidade, 9), a.control_id))
    return saida


@router.post("/auditar", response_model=RespostaAuditoria, dependencies=[Depends(limitar)])
async def post_auditar(
    file: Annotated[UploadFile, File()],
    contexto: Annotated[str, Form(max_length=MAX_CONTEXTO_CHARS)] = "",
) -> RespostaAuditoria:
    """Devolve a configuração corrigida e o relatório.

    `contexto` é opcional e descreve a carga (ex.: "coletor de log em
    DaemonSet"). Ele é **dado**: alimenta a contextualização da camada 3 e não
    influencia nem a detecção nem a verificação.
    """
    texto, nome = await _ler(file)
    return _resposta(_executar(texto, nome, contexto))


def _resposta(resultado) -> RespostaAuditoria:
    return RespostaAuditoria(
        arquivo=resultado.arquivo,
        formato=resultado.formato.value,
        total_de_problemas=len(resultado.achados),
        corrigidos_automaticamente=resultado.aplicacao.aplicados,
        dependem_de_voce=resultado.aplicacao.manuais,
        com_analise=resultado.com_analise,
        explicados_por_ia=resultado.explicados_por_ia,
        motivo_sem_ia=resultado.motivo_sem_ia,
        configuracao_corrigida=resultado.aplicacao.conteudo,
        relatorio_markdown=resultado.markdown,
        achados=_achados(resultado),
    )


@router.post(
    "/auditar/configuracao",
    response_class=PlainTextResponse,
    dependencies=[Depends(limitar)],
)
async def post_configuracao(file: Annotated[UploadFile, File()]) -> str:
    """Só o arquivo corrigido, em texto puro.

    Existe para o caso mais direto de todos: `curl ... > compose.yaml`.
    """
    texto, nome = await _ler(file)
    return _executar(texto, nome, "").aplicacao.conteudo


@router.get("/diagnostico")
def get_diagnostico() -> dict[str, object]:
    """Estado das camadas: por que veio (ou não veio) explicação de IA.

    Existe porque descobrir isso custou uma sessão inteira: a mensagem ao
    usuário dizia "não configurada" enquanto a configuração estava correta, e
    a investigação foi para o recurso errado. Uma chamada aqui responde.

    Informa presença, nunca valor — endpoint e client id não aparecem.
    """
    return diagnostico()


# --------------------------------------------------------------------------
# Progresso em tempo real
# --------------------------------------------------------------------------


@router.post("/auditar/stream", dependencies=[Depends(limitar)])
async def post_auditar_stream(
    file: Annotated[UploadFile, File()],
    contexto: Annotated[str, Form(max_length=MAX_CONTEXTO_CHARS)] = "",
) -> StreamingResponse:
    """Mesma auditoria, com os eventos das camadas conforme acontecem.

    Existe porque `/auditar` só responde depois de tudo pronto, e a espera é
    longa: medido, catorze achados levam quase dois minutos, dos quais ~99%
    são a camada 3. Sem streaming, qualquer indicador de progresso na tela
    seria coreografia inventada — bonita, e mentindo sobre o que o sistema
    está fazendo.

    Server-Sent Events e não WebSocket: o fluxo é de mão única e cabe em HTTP
    comum, sem handshake nem estado. Também não é *polling* com id de job:
    isso exigiria guardar estado entre requisições, e o Container App escala a
    zero e roda múltiplas réplicas — o job sumiria com a réplica.

    A resposta final vem no evento `resultado`, com o mesmo corpo de
    `/auditar`. O endpoint original continua existindo e inalterado, para quem
    integra por script e não quer saber de progresso.
    """
    texto, nome = await _ler(file)

    def eventos():
        fila: queue.Queue = queue.Queue()

        def emitir(evento: dict) -> None:
            fila.put(evento)

        def rodar() -> None:
            try:
                resultado = auditar(
                    texto, arquivo=nome, contexto=contexto, progresso=Progresso(emitir)
                )
                fila.put({"tipo": "resultado", "dados": _resposta(resultado).model_dump()})
            except Exception as exc:  # noqa: BLE001 - vira evento de erro, não 500 no meio do stream
                # Mesmo critério de `_executar`: o cliente recebe a frase
                # estável, o log recebe o que serve para depurar.
                _log.warning(
                    "falha durante a auditoria em stream",
                    extra={"erro": type(exc).__name__, "detalhe": str(exc), "arquivo": nome},
                )
                fila.put({"tipo": "erro", "detalhe": ERRO_DE_PARSE})
            finally:
                fila.put(None)

        # O pipeline é síncrono e demorado. Numa thread separada, os eventos
        # saem enquanto ele roda; no mesmo fluxo, sairiam todos no fim — que é
        # exatamente o problema que este endpoint existe para resolver.
        threading.Thread(target=rodar, daemon=True).start()

        while True:
            evento = fila.get()
            if evento is None:
                break
            yield f"data: {json.dumps(evento, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        eventos(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            # Sem isto, proxy com buffer segura os eventos e entrega tudo no
            # fim — o stream vira a resposta única que ele deveria substituir.
            "X-Accel-Buffering": "no",
        },
    )
