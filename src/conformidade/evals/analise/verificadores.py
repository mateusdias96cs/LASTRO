"""Verificações determinísticas sobre a saída do agente de análise.

O ponto central: **quase tudo que importa aqui é checável sem LLM.** Julgar
saída de LLM com outro LLM é caro, não-determinístico e transfere o problema —
o juiz também precisaria ser validado.

O que dá para verificar por asserção comum:

* citação é cópia literal do trecho fornecido — pega alucinação de fonte, que é
  a falha mais perigosa desta camada porque soa convincente;
* o chunk citado estava entre os fornecidos — pega fonte inventada;
* o controle analisado é o que foi enviado — pega achado inventado;
* veredito e severidade dentro do esperado;
* justificativa presente quando houve ajuste;
* idioma da resposta.

Sobra pouco de subjetivo (clareza da redação), e isso é revisão humana por
amostragem, não portão automático.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from conformidade.agents.analysis.contracts import (
    AchadoAnalisado,
    EntradaAnalise,
    Veredito,
)
from conformidade.agents.deterministic.models import SEVERITY_RANK, Severity


@dataclass(frozen=True)
class Falha:
    verificador: str
    detalhe: str


def _normalizar(texto: str) -> str:
    """Colapsa espaço e remove acento para comparar citação.

    O LLM reflui o texto — quebra de linha vira espaço, espaço duplo some. Uma
    comparação byte a byte reprovaria citação honesta. Já a remoção de acento
    protege contra diferença de normalização Unicode (NFC × NFD), que é
    invisível na tela e faz `in` falhar sem motivo aparente.

    O espaço antes de pontuação também sai. A extração de HTML deixa artefatos
    como `in the container's securityContext .` no nosso próprio corpus, e a
    primeira rodada real reprovou uma citação correta só por isso: o modelo
    escreveu a forma natural, `securityContext.`. Isso não afrouxa a checagem —
    uma frase inventada continua não casando; só deixa de punir o modelo por
    defeito da nossa ingestão.
    """
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"\s+", " ", texto).strip().lower()
    return re.sub(r"\s+([.,;:!?)\]])", r"\1", texto)


# --------------------------------------------------------------- citação


def citacoes_sao_literais(
    entrada: EntradaAnalise, saida: AchadoAnalisado, minimo_de_palavras: int = 4
) -> list[Falha]:
    """Todo `trecho_exato` precisa existir no chunk que ele diz citar."""
    falhas: list[Falha] = []
    if entrada.recuperacao is None:
        return falhas

    por_id = {t.chunk.chunk_id: t.chunk for t in entrada.recuperacao.trechos}

    for citacao in saida.citacoes:
        chunk = por_id.get(citacao.chunk_id)
        if chunk is None:
            falhas.append(
                Falha(
                    "citacao_de_fonte_inexistente",
                    f"chunk_id `{citacao.chunk_id}` não estava entre os fornecidos",
                )
            )
            continue

        if len(citacao.trecho_exato.split()) < minimo_de_palavras:
            falhas.append(
                Falha(
                    "citacao_curta_demais",
                    f"`{citacao.trecho_exato[:40]}` — citação de poucas palavras "
                    "casa por acaso e não sustenta afirmação",
                )
            )
            continue

        if _normalizar(citacao.trecho_exato) not in _normalizar(chunk.texto):
            falhas.append(
                Falha(
                    "citacao_nao_literal",
                    f"em `{citacao.chunk_id}`: «{citacao.trecho_exato[:70]}…» "
                    "não aparece no texto da fonte",
                )
            )

    return falhas


def exige_citacao(
    entrada: EntradaAnalise, saida: AchadoAnalisado, obrigatoria: bool
) -> list[Falha]:
    if not obrigatoria:
        return []
    if saida.citacoes:
        return []
    return [Falha("sem_citacao", "afirmação sem respaldo em fonte oficial")]


def nao_cita_distrator(
    entrada: EntradaAnalise, saida: AchadoAnalisado, proibidos: list[str]
) -> list[Falha]:
    """Nos pares confundíveis, citar a página errada produz afirmação
    plausível e errada — pior que não citar."""
    if entrada.recuperacao is None or not proibidos:
        return []
    por_id = {t.chunk.chunk_id: t.chunk for t in entrada.recuperacao.trechos}
    falhas = []
    for citacao in saida.citacoes:
        chunk = por_id.get(citacao.chunk_id)
        if chunk and chunk.page_id in proibidos:
            falhas.append(
                Falha(
                    "citou_distrator",
                    f"citou `{chunk.page_id}`, que trata de assunto vizinho e não deste controle",
                )
            )
    return falhas


# ------------------------------------------------------- escopo do agente


def nao_inventa_achado(entrada: EntradaAnalise, saida: AchadoAnalisado) -> list[Falha]:
    """A camada 3 analisa o achado que recebeu, não cria outro."""
    if saida.control_id != entrada.control_id:
        return [
            Falha(
                "controle_trocado",
                f"recebeu {entrada.control_id} e respondeu sobre {saida.control_id}",
            )
        ]
    return []


# ----------------------------------------------------- veredito e severidade


def veredito_esperado(saida: AchadoAnalisado, aceitos: list[str]) -> list[Falha]:
    if not aceitos or saida.veredito.value in aceitos:
        return []
    return [
        Falha(
            "veredito_inesperado",
            f"respondeu `{saida.veredito.value}`, esperado um de {aceitos}",
        )
    ]


def severidade_na_faixa(
    saida: AchadoAnalisado, minima: str | None, maxima: str | None
) -> list[Falha]:
    rank = SEVERITY_RANK[saida.severidade_ajustada]
    falhas = []
    if minima and rank < SEVERITY_RANK[Severity(minima)]:
        falhas.append(
            Falha(
                "severidade_baixa_demais",
                f"{saida.severidade_ajustada.value} abaixo do mínimo {minima}",
            )
        )
    if maxima and rank > SEVERITY_RANK[Severity(maxima)]:
        falhas.append(
            Falha(
                "severidade_alta_demais",
                f"{saida.severidade_ajustada.value} acima do máximo {maxima}",
            )
        )
    return falhas


def ajuste_justificado(entrada: EntradaAnalise, saida: AchadoAnalisado) -> list[Falha]:
    """Mudar severidade ou desviar de CONFIRMADO sem explicar é o caminho mais
    fácil para o agente 'resolver' um achado incômodo."""
    mudou_severidade = saida.severidade_ajustada != entrada.severidade_detectada
    desviou = saida.veredito != Veredito.CONFIRMADO
    if (mudou_severidade or desviou) and len(saida.justificativa_do_ajuste.split()) < 5:
        return [
            Falha(
                "ajuste_sem_justificativa",
                f"veredito `{saida.veredito.value}` / severidade "
                f"{entrada.severidade_detectada.value}→{saida.severidade_ajustada.value} "
                "sem justificativa",
            )
        ]
    return []


# --------------------------------------------------------------- conteúdo


_PALAVRAS_PT = ("não", "que", "para", "com", "container", "deve", "uso", "este", "isso")


def responde_em_portugues(saida: AchadoAnalisado) -> list[Falha]:
    texto = f"{saida.explicacao} {saida.como_corrigir}".lower()
    if not any(p in texto for p in _PALAVRAS_PT):
        return [Falha("idioma", "explicação não parece estar em português")]
    return []


def contem_algum(saida: AchadoAnalisado, alternativas: list[str]) -> list[Falha]:
    """Pelo menos um dos termos precisa aparecer.

    Existe porque exigir uma palavra específica vira checagem de estilo. Na
    primeira rodada real o modelo escreveu «mesmo com `:ro`, expõe a API do
    daemon» — substância exatamente certa — e reprovou por não usar a palavra
    "somente-leitura". O que se quer medir é se ele tratou do conceito, não
    qual sinônimo escolheu.
    """
    if not alternativas:
        return []
    texto = _normalizar(f"{saida.explicacao} {saida.como_corrigir} {saida.justificativa_do_ajuste}")
    if any(_normalizar(t) in texto for t in alternativas):
        return []
    return [Falha("nenhum_termo_equivalente", f"não mencionou nenhum de {alternativas}")]


def contem_termos(
    saida: AchadoAnalisado, obrigatorios: list[str], proibidos: list[str]
) -> list[Falha]:
    """Termos que a resposta precisa (ou não pode) conter.

    Usado para o que é objetivamente exigível — por exemplo, num achado não
    verificável estaticamente, a explicação precisa dizer que a imagem pode
    definir o usuário. Não é checagem de estilo.
    """
    texto = _normalizar(f"{saida.explicacao} {saida.como_corrigir} {saida.justificativa_do_ajuste}")
    falhas = []
    for termo in obrigatorios:
        if _normalizar(termo) not in texto:
            falhas.append(Falha("termo_obrigatorio_ausente", f"não mencionou «{termo}»"))
    for termo in proibidos:
        if _normalizar(termo) in texto:
            falhas.append(Falha("termo_proibido_presente", f"mencionou «{termo}»"))
    return falhas


def explicacao_substancial(saida: AchadoAnalisado, minimo: int = 15) -> list[Falha]:
    falhas = []
    if len(saida.explicacao.split()) < minimo:
        falhas.append(Falha("explicacao_rasa", f"{len(saida.explicacao.split())} palavras"))
    if len(saida.como_corrigir.split()) < 5:
        falhas.append(Falha("correcao_rasa", "correção sem conteúdo acionável"))
    return falhas
