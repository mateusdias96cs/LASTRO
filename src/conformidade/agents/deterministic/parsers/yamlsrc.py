"""Carregamento de YAML preservando o número de linha de cada mapa.

`yaml.safe_load` devolve dicts sem qualquer vínculo com o arquivo original, o
que deixaria todo achado de Compose/Kubernetes apontando para a linha 1. Aqui
os mapas viram `LineDict`, que carrega a linha onde o bloco começa.

`SafeLoader` é obrigatório: `yaml.load` completo instancia objetos Python
arbitrários a partir do arquivo do usuário — inaceitável num serviço que
recebe upload.
"""

from __future__ import annotations

from typing import Any

import yaml


class LineDict(dict):
    """dict que lembra as linhas do YAML (1-based).

    `start_line` é onde o bloco começa; `key_lines` guarda a linha de cada
    chave. Os dois são necessários porque não coincidem: em

        services:
          api:          <- linha 2, a chave
            image: x    <- linha 3, onde o bloco do valor começa

    o achado precisa apontar para a linha 2, que é onde a pessoa lê o nome do
    serviço, e não para a primeira propriedade dele.
    """

    __slots__ = ("start_line", "key_lines")

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.start_line: int | None = None
        self.key_lines: dict[str, int] = {}


class _LineLoader(yaml.SafeLoader):
    pass


def _construct_mapping(loader: _LineLoader, node: yaml.MappingNode) -> LineDict:
    loader.flatten_mapping(node)  # resolve as merge keys (`<<: *base`) do Compose
    mapping = LineDict(loader.construct_pairs(node, deep=True))
    mapping.start_line = node.start_mark.line + 1
    for key_node, _ in node.value:
        if isinstance(key_node, yaml.ScalarNode):
            mapping.key_lines[str(key_node.value)] = key_node.start_mark.line + 1
    return mapping


_LineLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping)


def line_of(obj: Any, default: int | None = None) -> int | None:
    return getattr(obj, "start_line", default) if isinstance(obj, dict) else default


def key_line(mapping: Any, key: str, default: int | None = None) -> int | None:
    """Linha onde a chave `key` foi declarada dentro de `mapping`."""
    if isinstance(mapping, dict):
        return getattr(mapping, "key_lines", {}).get(key, default)
    return default


def load_documents(content: str) -> tuple[list[Any], list[str]]:
    """Carrega um YAML multi-documento.

    Um documento inválido não invalida os outros: o erro é coletado e o parse
    segue, porque um manifesto quebrado no meio de um arquivo não deve zerar a
    auditoria dos demais.
    """
    docs: list[Any] = []
    errors: list[str] = []
    try:
        for doc in yaml.load_all(content, Loader=_LineLoader):
            if doc is not None:
                docs.append(doc)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        where = f" (linha {mark.line + 1})" if mark else ""
        errors.append(f"YAML inválido{where}: {getattr(exc, 'problem', exc)}")
    return docs, errors
