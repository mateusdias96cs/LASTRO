"""Redação de segredos na estrutura parseada.

As regras precisam ver o valor em claro para decidir se é segredo — mas o
relatório **não pode** carregá-lo. Redigir só a evidência do achado não basta:
a estrutura parseada devolvida junto (`ParsedArtifact`) contém o mesmo valor em
`env[].value` e, no caso do Dockerfile, no texto bruto da instrução.

Isso importa porque o relatório sai desta camada e vai para log estruturado,
para os próximos agentes e, no agente de análise, para dentro do prompt de um
LLM. Mandar credencial em claro para uma API externa é incidente, não bug de
formatação.

A sanitização roda **depois** da avaliação, no limite de saída: as regras
trabalham com a verdade, o mundo lá fora recebe o valor mascarado.
"""

from __future__ import annotations

from conformidade.agents.deterministic.models import ParsedArtifact
from conformidade.agents.deterministic.rules.shared import detect_secret, redact

# Abaixo disso, substituir a ocorrência no texto bruto causa mais estrago do
# que protege (um valor de 3 caracteres aparece em qualquer lugar).
_MIN_REPLACE_LEN = 6


def sanitize(artifact: ParsedArtifact) -> ParsedArtifact:
    """Devolve o artefato com todo valor suspeito de segredo mascarado."""
    literals: set[str] = set()

    # 1. Variáveis de ambiente das workloads.
    for workload in artifact.workloads:
        novos = []
        for var in workload.env:
            if var.value and not var.from_reference and detect_secret(var.name, var.value):
                literals.add(var.value)
                novos.append(var.model_copy(update={"value": redact(var.value)}))
            else:
                novos.append(var)
        workload.env = novos

    # 2. ENV/ARG do Dockerfile, que o parser preserva como texto bruto.
    if artifact.dockerfile is not None:
        for inst in artifact.dockerfile.instructions:
            if inst.keyword not in ("ENV", "ARG"):
                continue
            for pair in inst.value.split():
                name, sep, value = pair.partition("=")
                if sep and value and detect_secret(name, value):
                    literals.add(value)

    if not literals:
        return artifact

    replaceable = sorted((v for v in literals if len(v) >= _MIN_REPLACE_LEN), key=len, reverse=True)
    if replaceable and artifact.dockerfile is not None:
        # `instructions` e `stages[].instructions` referenciam os mesmos objetos,
        # então mutar aqui cobre as duas visões.
        for inst in artifact.dockerfile.instructions:
            for secret in replaceable:
                if secret in inst.value:
                    inst.value = inst.value.replace(secret, redact(secret))
                if secret in inst.raw:
                    inst.raw = inst.raw.replace(secret, redact(secret))

    # 3. Segredo passado como argumento de linha de comando.
    for workload in artifact.workloads:
        for field in ("entrypoint", "command", "args"):
            tokens = getattr(workload, field)
            if not tokens:
                continue
            setattr(
                workload,
                field,
                [_mask_token(tok, replaceable) for tok in tokens],
            )

    return artifact


def _mask_token(token: str, secrets: list[str]) -> str:
    for secret in secrets:
        if secret in token:
            token = token.replace(secret, redact(secret))
    return token
