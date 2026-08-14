"""Ponta a ponta: arquivo entra, configuração corrigida sai.

    from conformidade.pipeline import auditar
    print(auditar(open("compose.yaml").read(), "compose.yaml").markdown)

Encadeia as quatro camadas:

    1  parser + regras     detecta o achado a partir do arquivo
    2  recuperação         busca o respaldo oficial
    3  análise (LLM)       contextualiza e explica
    4  crítico + correção  verifica, conserta o arquivo e monta o relatório

## A camada 3 é opcional

A configuração corrigida sai da camada 1 mais o catálogo de patches — nada
disso passa por modelo. Sem Azure configurado, ou com a API fora do ar, o
usuário continua recebendo o arquivo pronto para colar; o que se perde é a
narrativa do "por quê" e a citação da fonte oficial.

Isso não é degradação acidental, é o desenho: o LLM explica, não decide. Fazer
a entrega principal depender dele seria colocar a parte não determinística no
caminho crítico de uma ferramenta de auditoria.

## O arquivo é dado

Nada do conteúdo enviado é interpretado como instrução em nenhuma camada. Onde
ele aparece no relatório, aparece como evidência recortada dentro de bloco de
código.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from conformidade.agents.analysis.contracts import (
    AchadoAnalisado,
    Confianca,
    EntradaAnalise,
    Veredito,
)
from conformidade.agents.critic import criticar
from conformidade.agents.critic.aplicar import Aplicacao, aplicar
from conformidade.agents.critic.contracts import AchadoCriticado, Formato
from conformidade.agents.deterministic import ArtifactKind, Finding, analyze

_log = logging.getLogger("conformidade.pipeline")

# Quantos trechos a camada 3 recebe. Medido: subir para 10 ganha um controle
# com respaldo e quase triplica a exposição a distratores.
K_TRECHOS = 6

_FORMATO = {
    ArtifactKind.DOCKERFILE: Formato.DOCKERFILE,
    ArtifactKind.DOCKER_COMPOSE: Formato.COMPOSE,
    ArtifactKind.KUBERNETES: Formato.KUBERNETES,
}


@dataclass
class Resultado:
    arquivo: str
    formato: Formato
    achados: list[Finding]
    aplicacao: Aplicacao
    criticados: list[tuple[EntradaAnalise, AchadoCriticado]] = field(default_factory=list)
    # Quantos achados a camada 3 de fato explicou. Contar em vez de um booleano
    # porque a degradação é PARCIAL: com o deployment limitado a poucas
    # requisições por minuto, um arquivo com dez achados pode ter três
    # explicados e sete no catálogo. Um `com_analise: true` nesse caso seria
    # verdadeiro e enganoso.
    explicados_por_ia: int = 0
    # Por que a camada 3 não participou, quando não participou. Vazio quando
    # participou em tudo.
    motivo_sem_ia: str = ""

    @property
    def com_analise(self) -> bool:
        return self.explicados_por_ia > 0

    @property
    def markdown(self) -> str:
        from conformidade.agents.critic.relatorio import em_markdown

        return em_markdown(self)


def _entrada(arquivo: str, achado: Finding, contexto: str, recuperacao) -> EntradaAnalise:
    return EntradaAnalise(
        arquivo=arquivo,
        control_id=achado.control_id,
        severidade_detectada=achado.severity,
        target=achado.target,
        linha=achado.location.start_line if achado.location else None,
        evidencia=achado.evidence,
        mensagem=achado.message,
        contexto=contexto,
        recuperacao=recuperacao,
    )


def _sem_analise(achado: Finding) -> AchadoAnalisado:
    """Achado sem passar pelo LLM: o que a camada 1 sabe, e nada além.

    Confiança alta porque a detecção é determinística — o que falta é a
    contextualização, não a certeza sobre o fato.
    """
    return AchadoAnalisado(
        control_id=achado.control_id,
        veredito=Veredito.CONFIRMADO,
        severidade_ajustada=achado.severity,
        explicacao=achado.message,
        como_corrigir=achado.remediation or "",
        citacoes=[],
        confianca=Confianca.ALTA,
    )


_SENTINELA = object()

# Etapas que o cliente vê. Os nomes são os das camadas, não passos internos —
# a interface mostra o sistema, não a implementação.
ETAPAS = ("deterministico", "recuperacao", "analise", "critico")


class Progresso:
    """Canal de progresso do pipeline para quem estiver observando.

    Existe porque a tela precisa mostrar a camada que está rodando AGORA, e a
    resposta única só chega quando tudo terminou. Sem isto, qualquer indicador
    de progresso seria coreografia inventada — bonita e mentirosa.

    O desequilíbrio entre as camadas é o motivo de o evento `analise` reportar
    achado a achado: medido, as camadas 1, 2 e 4 somam milissegundos e a 3
    responde por ~99% do tempo. Um indicador que trate as quatro como iguais
    fica parado no terceiro quarto e parece travado.
    """

    def __init__(self, emitir=None) -> None:
        self._emitir = emitir

    def etapa(self, nome: str, **dados) -> None:
        if self._emitir is not None:
            self._emitir({"tipo": "etapa", "etapa": nome, **dados})

    def analise(self, feitos: int, total: int) -> None:
        if self._emitir is not None:
            self._emitir({"tipo": "analise", "feitos": feitos, "total": total})


def auditar(
    conteudo: str,
    arquivo: str = "entrada.yaml",
    contexto: str = "",
    analisador=_SENTINELA,
    recuperador=_SENTINELA,
    progresso: Progresso | None = None,
) -> Resultado:
    """Roda as quatro camadas e devolve o resultado pronto para renderizar.

    Sem argumento, monta as camadas 2 e 3 de verdade. `None` explícito as
    desliga; um objeto as substitui, que é como a avaliação injeta duplos.

    A sentinela existe porque o padrão anterior era `None` e isso produziu um
    bug silencioso caro: a rota da API chamava `auditar(texto, arquivo=...)` sem
    passar nada, as camadas 2 e 3 ficavam desligadas, e o sistema em produção
    respondia sem citação nenhuma e com o aviso de "IA indisponível" em toda
    análise. O comportamento parecia um fallback sendo acionado por rate limit
    do Azure, e horas foram gastas investigando o lado errado. Agora o padrão é
    ligar; desligar exige dizer.
    """
    prog = progresso or Progresso()

    prog.etapa("deterministico")
    relatorio = analyze(conteudo, filename=arquivo)
    achados = list(relatorio.findings)
    formato = _FORMATO.get(relatorio.artifact.kind, Formato.COMPOSE)
    prog.etapa("deterministico", concluida=True, achados=len(achados), formato=formato.value)

    aplicacao = aplicar(conteudo, achados, formato)

    motivo = ""
    if recuperador is _SENTINELA:
        recuperador, falha = _recuperador_padrao()
        motivo = motivo or falha
    if analisador is _SENTINELA:
        analisador, falha = _analisador_padrao()
        motivo = motivo or falha

    prog.etapa("recuperacao")
    entradas = []
    for achado in achados:
        recuperacao = None
        if recuperador is not None:
            try:
                recuperacao = recuperador(achado.control_id)
            except Exception:  # noqa: BLE001 - fonte indisponível não derruba a auditoria
                recuperacao = None
        entradas.append((achado, _entrada(arquivo, achado, contexto, recuperacao)))
    prog.etapa("recuperacao", concluida=True)

    prog.etapa("analise", total=len(entradas))
    saidas, explicados, falha = _analisar_em_lote(entradas, analisador, prog)
    motivo = motivo or falha
    prog.etapa("analise", concluida=True, explicados=explicados)

    prog.etapa("critico")

    criticados: list[tuple[EntradaAnalise, AchadoCriticado]] = [
        (entrada, criticar(entrada, saida))
        for (_, entrada), saida in zip(entradas, saidas, strict=True)
    ]

    prog.etapa("critico", concluida=True)

    return Resultado(
        arquivo=arquivo,
        formato=formato,
        achados=achados,
        aplicacao=aplicacao,
        criticados=criticados,
        explicados_por_ia=explicados,
        motivo_sem_ia="" if explicados == len(achados) else motivo,
    )


# --------------------------------------------------------------------------
# Montagem das camadas 2 e 3
# --------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _retriever():
    """Índice híbrido, carregado uma vez e mantido em memória.

    1.271 chunks × 384 dimensões são ~2 MB e a busca exata custa menos de um
    milissegundo; recarregar por requisição desperdiçaria segundos à toa.
    """
    from conformidade.agents.retrieval.index import HybridRetriever, LexicalIndex
    from conformidade.agents.retrieval.index.build import (
        carregar_consultas,
        carregar_indice_denso,
        ler_meta,
    )
    from conformidade.agents.retrieval.ingest import carregar_chunks
    from conformidade.config import get_settings

    base = Path(get_settings().corpus_dir)
    chunks = carregar_chunks(base / "chunks.jsonl")
    denso = None
    consultas = None
    if (base / "index" / "vectors.npy").exists():
        denso = carregar_indice_denso(chunks, base / "index")
        consultas = carregar_consultas(base / "index")
    return HybridRetriever(
        chunks,
        lexical=LexicalIndex(chunks),
        denso=denso,
        vetores_de_consulta=consultas,
        corpus_versao=ler_meta(base / "index").get("corpus_versao", ""),
    )


def _recuperador_padrao():
    """`(recuperador, motivo)` — motivo preenchido quando não dá para montar."""
    from conformidade.agents.retrieval.queries import consulta_de

    try:
        retriever = _retriever()
    except (OSError, ValueError) as exc:
        return None, f"corpus indisponível: {exc}"

    def recuperar(control_id: str):
        consulta = consulta_de(control_id)
        if not consulta:
            return None
        return retriever.buscar(control_id, consulta, k=K_TRECHOS)

    return recuperar, ""


@lru_cache(maxsize=1)
def _analisador_ou_motivo():
    """Cliente do Azure, ou o motivo — específico — de não haver um.

    Em cache porque construir lê configuração e não muda entre requisições.

    ## Por que cada categoria tem mensagem própria

    A versão anterior capturava tudo e dizia "camada de IA não configurada".
    Isso custou uma sessão inteira de investigação no recurso errado: a
    mensagem afirmava falta de configuração, e a configuração estava correta.
    Mensagem de erro que descreve a causa errada é pior que mensagem genérica,
    porque direciona a busca para longe do problema.

    Note que o construtor **não toca a rede**: ele só lê configuração. Falha de
    credencial ou de permissão acontece na primeira análise, não aqui, e é
    reportada pelo laço em `auditar`.
    """
    from conformidade.agents.analysis.azure_provider import AnalisadorAzureOpenAI

    try:
        return AnalisadorAzureOpenAI(), ""
    except ValueError as exc:
        # Estado esperado em desenvolvimento local, não erro.
        _log.info(
            "camada 3 desativada: configuração ausente",
            extra={"erro": type(exc).__name__, "detalhe": str(exc)},
        )
        return None, f"AZURE_OPENAI_ENDPOINT ou AZURE_OPENAI_DEPLOYMENT ausente ({exc})"
    except ImportError as exc:
        _log.error(
            "camada 3 indisponível: dependência ausente na imagem",
            extra={"erro": type(exc).__name__, "detalhe": str(exc)},
        )
        return None, f"dependência ausente na imagem: {exc}"
    except Exception as exc:  # noqa: BLE001 - a camada 3 nunca derruba a auditoria
        _log.exception(
            "camada 3 indisponível: falha inesperada ao montar o analisador",
            extra={"erro": type(exc).__name__, "detalhe": str(exc)},
        )
        return None, f"falha ao montar a camada de IA — {type(exc).__name__}: {exc}"


def _analisador_padrao():
    return _analisador_ou_motivo()


def diagnostico() -> dict[str, object]:
    """Estado das camadas, para responder "por que não veio explicação?" numa
    chamada em vez de numa sessão de investigação.

    Não expõe segredo: informa se cada peça está de pé e, quando não está, por
    quê. O endpoint que serve isto é `GET /api/v1/diagnostico`.
    """
    from conformidade.config import get_settings

    settings = get_settings()
    recuperador, falha_busca = _recuperador_padrao()
    analisador, falha_ia = _analisador_padrao()

    # A credencial é exercitada de verdade: PEDE UM TOKEN.
    #
    # A versão anterior só chamava `_obter_cliente()` e reportava "ok". Isso
    # era mentira útil demais para deixar passar: `get_bearer_token_provider`
    # devolve um callable e não fala com o Azure — o token só é buscado no
    # primeiro uso. O endpoint dizia "credencial ok" enquanto toda análise
    # falhava com `ClientAuthenticationError`, que é exatamente o tipo de
    # diagnóstico enganoso que ele existe para eliminar.
    token = "não testado"
    if analisador is not None:
        try:
            from azure.identity import DefaultAzureCredential

            from conformidade.agents.analysis.azure_provider import ESCOPO_COGNITIVE_SERVICES

            credencial = DefaultAzureCredential(
                managed_identity_client_id=settings.azure_client_id or None
            )
            credencial.get_token(ESCOPO_COGNITIVE_SERVICES)
            token = "ok"
        except Exception as exc:  # noqa: BLE001 - diagnóstico não pode falhar
            # Só a primeira linha: o erro da credencial traz a cadeia inteira
            # de tentativas, e o resto vai para o log.
            primeira = str(exc).split("\n")[0]
            token = f"{type(exc).__name__}: {primeira}"
            _log.warning(
                "credencial da camada 3 não obteve token",
                extra={"erro": type(exc).__name__, "detalhe": str(exc)},
            )

    return {
        "camada_2_busca": "ok" if recuperador else falha_busca,
        "camada_3_configurada": analisador is not None,
        "camada_3_motivo": falha_ia,
        "camada_3_credencial": token,
        # Presença, nunca valor.
        "endpoint_definido": bool(settings.azure_openai_endpoint),
        "deployment_definido": bool(settings.azure_openai_deployment),
        "client_id_definido": bool(settings.azure_client_id),
        "corpus_dir": settings.corpus_dir,
    }


def _analisar_em_lote(entradas, analisador, prog: Progresso | None = None):
    """Chama a camada 3 em paralelo, preservando a ordem dos achados.

    Sequencial, nove achados levavam quase três minutos — o modelo de
    raciocínio gasta ~20s por chamada, e nenhum navegador espera isso. Em
    paralelo o tempo cai para o de uma rodada mais a fila.

    Threads e não `asyncio`: o SDK do OpenAI aqui é síncrono, e a espera é de
    rede. Reescrevê-lo para assíncrono só para paralelizar E/S seria trocar o
    caminho inteiro da camada 3 por ganho nenhum.

    A ordem da saída acompanha a das entradas, não a de conclusão — relatório
    de auditoria precisa sair igual a cada execução com a mesma entrada.
    """
    prog = prog or Progresso()
    if analisador is None:
        prog.analise(len(entradas), len(entradas))
        return [_sem_analise(a) for a, _ in entradas], 0, ""

    from concurrent.futures import ThreadPoolExecutor

    from conformidade.config import get_settings

    limite = max(1, get_settings().analise_paralela)
    saidas: list = [None] * len(entradas)
    explicados = 0
    falha = ""

    def trabalho(indice):
        achado, entrada = entradas[indice]
        try:
            return indice, analisador.analisar(entrada), None
        except Exception as exc:  # noqa: BLE001 - o arquivo corrigido não depende do LLM
            # Degradação por achado, não por requisição: estourar a cota
            # derruba alguns e os outros continuam valendo.
            _log.warning(
                "camada 3 falhou neste achado",
                extra={
                    "control_id": achado.control_id,
                    "erro": type(exc).__name__,
                    "detalhe": str(exc),
                },
            )
            return indice, _sem_analise(achado), exc

    concluidos = 0
    with ThreadPoolExecutor(max_workers=min(limite, len(entradas) or 1)) as pool:
        for indice, saida, exc in pool.map(trabalho, range(len(entradas))):
            saidas[indice] = saida
            concluidos += 1
            prog.analise(concluidos, len(entradas))
            if exc is None:
                explicados += 1
            elif not falha:
                falha = f"{type(exc).__name__}: {exc}"

    return saidas, explicados, falha
