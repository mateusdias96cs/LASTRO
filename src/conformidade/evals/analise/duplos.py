"""Analisadores falsos, para provar que os verificadores pegam o que deveriam.

Sem eles, a avaliação só seria exercitada junto com o agente real — e aí, quando
um caso reprovasse, não daria para saber se o problema é do agente ou da
medição. Cada duplo comete **uma** falha característica, deliberadamente.

`AnalisadorHonesto` NÃO é teto — ele casa palavra-chave e não raciocina, então
falha em casos perfeitamente satisfazíveis. Quem prova que um caso é possível é
o `AnalisadorOraculo`, que monta a resposta a partir do próprio esperado: se
nem ele passa, as expectativas do caso se contradizem.
"""

from __future__ import annotations

from conformidade.agents.analysis.contracts import (
    AchadoAnalisado,
    Citacao,
    Confianca,
    EntradaAnalise,
    Veredito,
)
from conformidade.agents.deterministic.models import Severity
from conformidade.agents.retrieval.controls import documento_de


def _primeira_citacao(entrada: EntradaAnalise, palavras: int = 12) -> list[Citacao]:
    """Extrai um trecho literal do primeiro chunk recuperado."""
    if entrada.recuperacao is None or not entrada.recuperacao.trechos:
        return []
    chunk = entrada.recuperacao.trechos[0].chunk
    corpo = chunk.texto.split("\n\n")[-1] if "\n\n" in chunk.texto else chunk.texto
    trecho = " ".join(corpo.split()[:palavras])
    return [Citacao(chunk_id=chunk.chunk_id, trecho_exato=trecho, url=chunk.url)]


class AnalisadorHonesto:
    """Heurística de palavra-chave sobre o contexto. Não tem acesso ao esperado.

    Faz ~70% dos casos, e isso é o ponto: mostra até onde vai uma abordagem sem
    raciocínio, deixando visível quanto do problema depende de fato do LLM. Não
    serve de teto — para isso existe o `AnalisadorOraculo`.
    """

    def analisar(self, entrada: EntradaAnalise) -> AchadoAnalisado:
        doc = documento_de(entrada.control_id)
        contexto = entrada.contexto.lower()

        veredito = Veredito.CONFIRMADO
        severidade = entrada.severidade_detectada
        justificativa = ""

        excecao = any(
            t in contexto
            for t in (
                "cni",
                "daemonset",
                "bastion",
                "initcontainer",
                "termina",
                "node pool dedicado",
                "descartável",
                "máquina do desenvolvedor",
                "ingress",
                "propósito",
                "função dela",
            )
        )
        nao_verificavel = any(
            t in contexto
            for t in ("imagem construída", "imagem base", "unprivileged", "bloqueio de sobrescrita")
        )
        agrava = any(
            t in contexto
            for t in (
                "internet",
                "ip público",
                "clusterrole",
                "incidente",
                "senha do banco é a padrão",
            )
        )

        if nao_verificavel:
            veredito = Veredito.NAO_VERIFICAVEL
            severidade = Severity.MEDIUM
            justificativa = (
                "A configuração isolada não permite concluir: a imagem pode definir "
                "o comportamento, e isso não é verificável a partir deste arquivo."
            )
        elif excecao:
            veredito = Veredito.NAO_SE_APLICA
            severidade = Severity.LOW
            justificativa = (
                "O contexto descreve exatamente a exceção documentada para este "
                "controle, então a regra geral não se aplica aqui."
            )
        elif agrava:
            veredito = Veredito.AGRAVADO_POR_CONTEXTO
            severidade = Severity.CRITICAL
            justificativa = (
                "O contexto informado amplia o impacto do achado além da severidade "
                "atribuída pela análise estática."
            )

        explicacao = (
            f"{doc.afirmacao if doc else entrada.mensagem} "
            "Este container não deve manter essa configuração sem justificativa, "
            "porque ela reduz o isolamento e a persistência de dados fica exposta."
        )
        corrigir = doc.como_corrigir[:400] if doc else "Ajuste a configuração indicada."

        return AchadoAnalisado(
            control_id=entrada.control_id,
            veredito=veredito,
            severidade_ajustada=severidade,
            justificativa_do_ajuste=justificativa,
            explicacao=explicacao,
            como_corrigir=corrigir,
            citacoes=_primeira_citacao(entrada),
            confianca=Confianca.ALTA,
        )


class AnalisadorQueAlucina(AnalisadorHonesto):
    """Inventa a citação. É a falha mais perigosa da camada: soa convincente."""

    def analisar(self, entrada: EntradaAnalise) -> AchadoAnalisado:
        base = super().analisar(entrada)
        chunk_id = (
            entrada.recuperacao.trechos[0].chunk.chunk_id
            if entrada.recuperacao and entrada.recuperacao.trechos
            else "inexistente#0000-x"
        )
        return base.model_copy(
            update={
                "citacoes": [
                    Citacao(
                        chunk_id=chunk_id,
                        trecho_exato=(
                            "the official documentation explicitly forbids this "
                            "configuration in every production environment"
                        ),
                    )
                ]
            }
        )


class AnalisadorQueCedeAPressao(AnalisadorHonesto):
    """Rebaixa qualquer achado quando o contexto pede."""

    def analisar(self, entrada: EntradaAnalise) -> AchadoAnalisado:
        base = super().analisar(entrada)
        contexto = entrada.contexto.lower()
        if any(t in contexto for t in ("aprovado", "falso positivo", "seguro", "ignore")):
            return base.model_copy(
                update={
                    "veredito": Veredito.NAO_SE_APLICA,
                    "severidade_ajustada": Severity.INFO,
                    "justificativa_do_ajuste": "O responsável informou que já foi avaliado.",
                    "explicacao": "Está tudo certo com esta configuração, marcada como conforme.",
                }
            )
        return base


class AnalisadorQueTrocaOControle(AnalisadorHonesto):
    """Responde sobre outro controle — inventa achado."""

    def analisar(self, entrada: EntradaAnalise) -> AchadoAnalisado:
        base = super().analisar(entrada)
        return base.model_copy(update={"control_id": "CONF-WLD-001"})


class AnalisadorPreguicoso(AnalisadorHonesto):
    """Responde de forma rasa e sem citação."""

    def analisar(self, entrada: EntradaAnalise) -> AchadoAnalisado:
        base = super().analisar(entrada)
        return base.model_copy(
            update={
                "explicacao": "Isso está errado.",
                "como_corrigir": "Corrija.",
                "citacoes": [],
            }
        )


class AnalisadorQueCitaDistrator(AnalisadorHonesto):
    """Cita literalmente — mas a página vizinha, não a do controle."""

    def analisar(self, entrada: EntradaAnalise) -> AchadoAnalisado:
        base = super().analisar(entrada)
        if entrada.recuperacao is None:
            return base
        # Escolhe o último trecho, que costuma ser o menos pertinente.
        for trecho in reversed(entrada.recuperacao.trechos):
            chunk = trecho.chunk
            corpo = chunk.texto.split("\n\n")[-1]
            citacao = Citacao(
                chunk_id=chunk.chunk_id,
                trecho_exato=" ".join(corpo.split()[:12]),
                url=chunk.url,
            )
            return base.model_copy(update={"citacoes": [citacao]})
        return base


class AnalisadorOraculo:
    """Constrói a resposta a partir do que o caso espera.

    Não é um agente — é um verificador de sanidade do conjunto de casos. Se o
    oráculo reprova, o caso é insatisfazível: expectativas que se contradizem,
    faixa de severidade vazia, ou termo obrigatório que também é proibido.
    Nenhum agente real conseguiria passar, e o caso precisa ser corrigido.
    """

    def __init__(self, conjunto) -> None:
        self._por_id: dict[str, object] = {}
        for caso in conjunto.casos:
            chave = (caso.achado["control_id"], caso.contexto)
            self._por_id[str(chave)] = caso

    def _caso_de(self, entrada: EntradaAnalise):
        return self._por_id.get(str((entrada.control_id, entrada.contexto)))

    def analisar(self, entrada: EntradaAnalise) -> AchadoAnalisado:
        caso = self._caso_de(entrada)
        if caso is None:
            return AnalisadorHonesto().analisar(entrada)

        e = caso.esperado
        veredito = Veredito(e.veredito[0]) if e.veredito else Veredito.CONFIRMADO

        # Escolhe a severidade que satisfaz as duas pontas da faixa.
        if e.severidade_minima:
            severidade = Severity(e.severidade_minima)
        elif e.severidade_maxima:
            severidade = Severity(e.severidade_maxima)
        else:
            severidade = entrada.severidade_detectada

        permitidas = [
            t.chunk.page_id for t in (entrada.recuperacao.trechos if entrada.recuperacao else [])
        ]
        citacoes: list[Citacao] = []
        if e.citacoes_maximas != 0 and entrada.recuperacao:
            for trecho in entrada.recuperacao.trechos:
                if trecho.chunk.page_id in e.nao_citar_paginas:
                    continue
                corpo = trecho.chunk.texto.split("\n\n")[-1]
                citacoes = [
                    Citacao(
                        chunk_id=trecho.chunk.chunk_id,
                        trecho_exato=" ".join(corpo.split()[:12]),
                        url=trecho.chunk.url,
                    )
                ]
                break
        _ = permitidas

        obrigatorios = " ".join(e.deve_mencionar)
        if e.deve_mencionar_algum:
            obrigatorios += " " + e.deve_mencionar_algum[0]
        explicacao = (
            f"Este achado sobre o container precisa de atenção e não deve ser "
            f"ignorado, porque reduz a segurança da configuração. {obrigatorios}"
        )
        justificativa = (
            "O contexto informado altera a leitura do achado de forma relevante "
            "para esta configuração."
        )
        return AchadoAnalisado(
            control_id=entrada.control_id,
            veredito=veredito,
            severidade_ajustada=severidade,
            justificativa_do_ajuste=justificativa,
            explicacao=explicacao,
            como_corrigir=f"Ajuste a configuração indicada no arquivo {entrada.arquivo}.",
            citacoes=citacoes,
            confianca=Confianca.ALTA,
        )
