"""Carga e validação dos casos de avaliação da camada 3."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from conformidade.agents.analysis.contracts import EntradaAnalise, Veredito
from conformidade.agents.deterministic.models import Severity

RAIZ = Path(__file__).resolve().parents[4]
CAMINHO_CASOS = RAIZ / "evals" / "analise_casos.yaml"


class Esperado(BaseModel):
    """O que a resposta precisa satisfazer. Tudo aqui é verificável sem LLM."""

    veredito: list[str] = Field(default_factory=list)
    severidade_minima: str | None = None
    severidade_maxima: str | None = None
    exige_citacao: bool = False
    citacoes_maximas: int | None = None
    deve_mencionar: list[str] = Field(default_factory=list)
    deve_mencionar_algum: list[str] = Field(default_factory=list)
    nao_deve_mencionar: list[str] = Field(default_factory=list)
    nao_citar_paginas: list[str] = Field(default_factory=list)


class Caso(BaseModel):
    id: str
    nivel: int
    descricao: str = ""
    achado: dict[str, Any]
    contexto: str = ""
    recuperacao: str = "real"  # "real" | "vazia"
    esperado: Esperado

    def para_entrada(self, recuperacao: Any = None) -> EntradaAnalise:
        a = self.achado
        return EntradaAnalise(
            arquivo=a["arquivo"],
            control_id=a["control_id"],
            severidade_detectada=Severity(a["severidade"]),
            target=a.get("target"),
            linha=a.get("linha"),
            evidencia=a.get("evidencia"),
            mensagem=a.get("mensagem", ""),
            contexto=self.contexto,
            recuperacao=recuperacao,
        )


class Conjunto(BaseModel):
    versao: int
    casos: list[Caso]
    taxa_minima_por_nivel: dict[int, float] = Field(default_factory=dict)
    citacoes_nao_literais_maximas: int = 0

    def por_nivel(self) -> dict[int, list[Caso]]:
        saida: dict[int, list[Caso]] = {}
        for caso in self.casos:
            saida.setdefault(caso.nivel, []).append(caso)
        return dict(sorted(saida.items()))


def carregar(caminho: Path = CAMINHO_CASOS) -> Conjunto:
    dados = yaml.safe_load(caminho.read_text(encoding="utf-8"))
    limiares = dados.get("limiares", {})
    return Conjunto(
        versao=dados["versao"],
        casos=[Caso(**c) for c in dados["casos"]],
        taxa_minima_por_nivel={
            int(k): float(v) for k, v in (limiares.get("taxa_minima_por_nivel") or {}).items()
        },
        citacoes_nao_literais_maximas=int(limiares.get("citacoes_nao_literais", 0)),
    )


def validar(conjunto: Conjunto, controles_do_catalogo: set[str]) -> list[str]:
    """Integridade do conjunto. Vazia = íntegro."""
    problemas: list[str] = []

    ids = [c.id for c in conjunto.casos]
    duplicados = {i for i in ids if ids.count(i) > 1}
    if duplicados:
        problemas.append(f"ids duplicados: {sorted(duplicados)}")

    vereditos_validos = {v.value for v in Veredito}
    severidades_validas = {s.value for s in Severity}

    for caso in conjunto.casos:
        cid = caso.achado.get("control_id")
        if cid not in controles_do_catalogo:
            problemas.append(f"{caso.id}: controle desconhecido `{cid}`")

        if caso.achado.get("severidade") not in severidades_validas:
            problemas.append(f"{caso.id}: severidade inválida")

        desconhecidos = set(caso.esperado.veredito) - vereditos_validos
        if desconhecidos:
            problemas.append(f"{caso.id}: veredito inexistente {sorted(desconhecidos)}")

        for campo in ("severidade_minima", "severidade_maxima"):
            valor = getattr(caso.esperado, campo)
            if valor and valor not in severidades_validas:
                problemas.append(f"{caso.id}: {campo} inválida `{valor}`")

        if caso.recuperacao not in ("real", "vazia"):
            problemas.append(f"{caso.id}: recuperacao `{caso.recuperacao}` desconhecida")

        # Um caso sem nenhuma expectativa passa sempre e não mede nada.
        e = caso.esperado
        if not (
            e.veredito
            or e.deve_mencionar
            or e.deve_mencionar_algum
            or e.nao_citar_paginas
            or e.exige_citacao
        ):
            problemas.append(f"{caso.id}: sem nenhuma expectativa verificável")

        # Contradição entre a avaliação e o próprio sistema: o prompt manda
        # deixar `citacoes` vazio para controle sem respaldo declarado, e o
        # caso exigiria citação. O modelo obedece ao prompt e reprova por
        # isso — falha garantida que não mede nada do agente.
        if e.exige_citacao:
            from conformidade.agents.retrieval.cobertura import SEM_RESPALDO_OFICIAL

            if cid in SEM_RESPALDO_OFICIAL:
                problemas.append(
                    f"{caso.id}: exige citação de `{cid}`, que está declarado em "
                    "SEM_RESPALDO_OFICIAL — o prompt manda não citar"
                )

    niveis_usados = {c.nivel for c in conjunto.casos}
    sem_limiar = niveis_usados - set(conjunto.taxa_minima_por_nivel)
    if sem_limiar:
        problemas.append(f"níveis sem taxa mínima definida: {sorted(sem_limiar)}")

    return problemas
