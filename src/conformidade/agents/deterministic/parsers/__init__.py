"""Parsers por formato, todos escritos do zero."""

from conformidade.agents.deterministic.parsers.compose import parse_compose
from conformidade.agents.deterministic.parsers.dockerfile import parse_dockerfile
from conformidade.agents.deterministic.parsers.kubernetes import parse_kubernetes

__all__ = ["parse_compose", "parse_dockerfile", "parse_kubernetes"]
