"""Conjunto de regras.

Os módulos são importados aqui só pelo efeito colateral de registrar as regras
no `registry`. Sem este import, o registro fica vazio e a análise não acha nada.
"""

from conformidade.agents.deterministic.rules import (  # noqa: F401
    compose_rules,
    dockerfile_rules,
    kubernetes_rules,
    workload_rules,
)
from conformidade.agents.deterministic.rules.base import Observation, Rule, registry

__all__ = ["Observation", "Rule", "registry"]
