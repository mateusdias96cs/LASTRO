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


def auditar(
    conteudo: str,
    arquivo: str = "entrada.yaml",
    contexto: str = "",
    analisador=_SENTINELA,
    recuperador=_SENTINELA,
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
    relatorio = analyze(conteudo, filename=arquivo)
    achados = list(relatorio.findings)
    formato = _FORMATO.get(relatorio.artifact.kind, Formato.COMPOSE)

    aplicacao = aplicar(conteudo, achados, formato)

    motivo = ""
    if recuperador is _SENTINELA:
        recuperador, falha = _recuperador_padrao()
        motivo = motivo or falha
    if analisador is _SENTINELA:
        analisador, falha = _analisador_padrao()
        motivo = motivo or falha

    criticados: list[tuple[EntradaAnalise, AchadoCriticado]] = []
    explicados = 0

    for achado in achados:
        recuperacao = None
        if recuperador is not None:
            try:
                recuperacao = recuperador(achado.control_id)
            except Exception:  # noqa: BLE001 - fonte indisponível não derruba a auditoria
                recuperacao = None

        entrada = _entrada(arquivo, achado, contexto, recuperacao)
        if analisador is None:
            saida = _sem_analise(achado)
        else:
            try:
                saida = analisador.analisar(entrada)
                explicados += 1
            except Exception as exc:  # noqa: BLE001 - o arquivo corrigido não depende do LLM
                # Degradação por achado, não por requisição: o limite de
                # requisições por minuto do deployment derruba os últimos de um
                # arquivo grande, e os primeiros continuam valendo.
                saida = _sem_analise(achado)
                motivo = motivo or f"{type(exc).__name__}: {exc}"
        criticados.append((entrada, criticar(entrada, saida)))

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
    """Cliente do Azure, ou o motivo de não haver um.

    Em cache porque construir envolve resolver credencial gerenciada, o que
    custa uma ida à rede e não muda entre requisições.
    """
    from conformidade.agents.analysis.azure_provider import AnalisadorAzureOpenAI

    try:
        return AnalisadorAzureOpenAI(), ""
    except ValueError as exc:
        # Falta de configuração é estado esperado em desenvolvimento local, não
        # erro: o arquivo corrigido não depende da camada 3.
        return None, f"camada de IA não configurada ({exc})"


def _analisador_padrao():
    return _analisador_ou_motivo()
