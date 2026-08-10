"""Carga e validação do gabarito.

O gabarito é declarado no **nível de página**, não de chunk. Decisão deliberada:
assim, mudar o tamanho do chunk na Fase 4 não invalida o gabarito. Um trecho
conta como acerto se veio da página esperada.

A validação é tão importante quanto o gabarito: ela impede que manifesto,
catálogo e gabarito saiam de sincronia sem ninguém perceber.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

RAIZ = Path(__file__).resolve().parents[3]
CAMINHO_GABARITO = RAIZ / "evals" / "golden.yaml"
CAMINHO_FONTES = RAIZ / "corpus" / "sources.yaml"

# Ganho por grau de relevância, usado no nDCG.
GANHO = {"alta": 3.0, "apoio": 1.0}


class CasoGabarito(BaseModel):
    control_id: str
    alta: list[str] = Field(default_factory=list)
    apoio: list[str] = Field(default_factory=list)
    nao_deve: list[str] = Field(default_factory=list)
    sem_cobertura_oficial: bool = False
    nota: str = ""

    @property
    def relevantes(self) -> set[str]:
        return set(self.alta) | set(self.apoio)

    @property
    def ganhos(self) -> dict[str, float]:
        ganhos = {p: GANHO["apoio"] for p in self.apoio}
        ganhos.update({p: GANHO["alta"] for p in self.alta})
        return ganhos


class Gabarito(BaseModel):
    versao: int
    casos: dict[str, CasoGabarito]
    limiares: dict[str, float] = Field(default_factory=dict)

    def caso(self, control_id: str) -> CasoGabarito | None:
        return self.casos.get(control_id)


def carregar_paginas_do_manifesto(caminho: Path = CAMINHO_FONTES) -> set[str]:
    dados: dict[str, Any] = yaml.safe_load(caminho.read_text(encoding="utf-8"))
    return {p["id"] for p in dados.get("paginas", [])}


def carregar_gabarito(caminho: Path = CAMINHO_GABARITO) -> Gabarito:
    dados: dict[str, Any] = yaml.safe_load(caminho.read_text(encoding="utf-8"))
    casos = {
        control_id: CasoGabarito(control_id=control_id, **(corpo or {}))
        for control_id, corpo in (dados.get("casos") or {}).items()
    }
    return Gabarito(versao=dados["versao"], casos=casos, limiares=dados.get("limiares", {}))


def validar(gabarito: Gabarito, controles_do_catalogo: set[str]) -> list[str]:
    """Devolve a lista de inconsistências. Vazia = gabarito íntegro."""
    problemas: list[str] = []
    paginas = carregar_paginas_do_manifesto()

    faltando = controles_do_catalogo - set(gabarito.casos)
    if faltando:
        problemas.append(f"controles do catálogo sem caso no gabarito: {sorted(faltando)}")

    orfaos = set(gabarito.casos) - controles_do_catalogo
    if orfaos:
        problemas.append(f"casos no gabarito sem controle correspondente: {sorted(orfaos)}")

    for control_id, caso in sorted(gabarito.casos.items()):
        referenciadas = set(caso.alta) | set(caso.apoio) | set(caso.nao_deve)
        desconhecidas = referenciadas - paginas
        if desconhecidas:
            problemas.append(f"{control_id}: páginas fora do manifesto: {sorted(desconhecidas)}")
        sobreposicao = set(caso.nao_deve) & caso.relevantes
        if sobreposicao:
            problemas.append(
                f"{control_id}: página marcada como relevante e distrator: {sorted(sobreposicao)}"
            )
        if not caso.sem_cobertura_oficial and not caso.alta:
            problemas.append(
                f"{control_id}: sem nenhuma página de alta relevância e não marcado "
                "como sem_cobertura_oficial"
            )

    return problemas
