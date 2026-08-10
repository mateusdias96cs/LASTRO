"""Parser de Dockerfile escrito do zero.

Trata o que a sintaxe real exige e que um `split('\\n')` ingênuo erra:

* diretivas de parser (`# syntax=`, `# escape=`) — e `escape` muda o caractere
  de continuação, o que altera todo o resto do parse;
* continuação de linha, inclusive com **comentários no meio** da continuação,
  que precisam ser descartados sem quebrar a instrução;
* heredocs (`RUN <<EOF ... EOF`), sintaxe moderna que engoliria linhas soltas
  e faria o parser interpretar shell como instrução;
* forma JSON (exec) vs. forma shell em CMD/ENTRYPOINT/RUN;
* flags de instrução (`--from=`, `--chown=`, `--mount=`);
* multi-stage, com `FROM builder` referenciando stage e não imagem externa.

Os números de linha são preservados por instrução: sem eles o achado não
consegue apontar para o lugar certo do arquivo.
"""

from __future__ import annotations

import json
import re
import shlex

from conformidade.agents.deterministic.models import (
    DockerfileSpec,
    DockerInstruction,
    DockerStage,
    EnvVar,
    ImageRef,
    MountType,
    PortBinding,
    SecurityPosture,
    SourceLocation,
    VolumeMount,
    Workload,
    WorkloadKind,
)

KNOWN_INSTRUCTIONS = frozenset(
    {
        "FROM",
        "RUN",
        "CMD",
        "LABEL",
        "MAINTAINER",
        "EXPOSE",
        "ENV",
        "ADD",
        "COPY",
        "ENTRYPOINT",
        "VOLUME",
        "USER",
        "WORKDIR",
        "ARG",
        "ONBUILD",
        "STOPSIGNAL",
        "HEALTHCHECK",
        "SHELL",
    }
)

_DIRECTIVE_RE = re.compile(r"^#\s*([A-Za-z][A-Za-z0-9_]*)\s*=\s*(\S+)\s*$")
_KNOWN_DIRECTIVES = frozenset({"syntax", "escape", "check"})
_FLAG_RE = re.compile(r"^--([A-Za-z0-9][A-Za-z0-9-]*)(?:=(\S+))?\s*")
_HEREDOC_RE = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
_FROM_RE = re.compile(r"^(?P<image>\S+)(?:\s+[Aa][Ss]\s+(?P<name>\S+))?\s*$")


def _split_flags(value: str) -> tuple[dict[str, str], str]:
    """Extrai as flags do início da instrução e devolve o resto."""
    flags: dict[str, str] = {}
    rest = value.lstrip()
    while True:
        m = _FLAG_RE.match(rest)
        if not m:
            break
        flags[m.group(1)] = m.group(2) if m.group(2) is not None else "true"
        rest = rest[m.end() :].lstrip()
    return flags, rest


def _safe_shlex(text: str) -> list[str]:
    try:
        return shlex.split(text)
    except ValueError:
        # Aspas desbalanceadas: cai para split simples em vez de estourar.
        return text.split()


def _parse_json_form(value: str) -> list[str] | None:
    v = value.strip()
    if not (v.startswith("[") and v.endswith("]")):
        return None
    try:
        parsed = json.loads(v)
    except (ValueError, TypeError):
        return None
    if isinstance(parsed, list) and all(isinstance(x, str) for x in parsed):
        return parsed
    return None


def _tokenize(content: str) -> tuple[dict[str, str], list[DockerInstruction]]:
    lines = content.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if lines and lines[0].startswith("﻿"):
        lines[0] = lines[0].lstrip("﻿")

    directives: dict[str, str] = {}
    escape_char = "\\"
    i = 0

    # Bloco de diretivas: só vale antes de qualquer outra coisa no arquivo.
    while i < len(lines):
        m = _DIRECTIVE_RE.match(lines[i].strip())
        if not m or m.group(1).lower() not in _KNOWN_DIRECTIVES:
            break
        key, val = m.group(1).lower(), m.group(2)
        directives[key] = val
        if key == "escape" and val in ("\\", "`"):
            escape_char = val
        i += 1

    instructions: list[DockerInstruction] = []

    while i < len(lines):
        stripped = lines[i].strip()
        if not stripped or stripped.startswith("#"):
            i += 1
            continue

        start_line = i + 1
        parts: list[str] = []
        cur = lines[i]

        # Junta continuações, pulando comentários intercalados.
        while True:
            body = cur.rstrip()
            if body.endswith(escape_char):
                parts.append(body[:-1])
                i += 1
                while i < len(lines) and lines[i].strip().startswith("#"):
                    i += 1
                if i >= len(lines):
                    break
                cur = lines[i]
            else:
                parts.append(body)
                break

        joined = " ".join(p.strip() for p in parts if p.strip())
        raw_end = i

        m = re.match(r"^(\S+)\s*(.*)$", joined, re.DOTALL)
        if not m:
            i += 1
            continue
        keyword = m.group(1).upper()
        value = m.group(2).strip()

        # Heredoc: consome o corpo até o terminador para que essas linhas não
        # sejam lidas como instruções soltas.
        heredoc_body: list[str] = []
        terminators = [t[1] for t in _HEREDOC_RE.findall(value)]
        for term in terminators:
            i += 1
            while i < len(lines) and lines[i].strip() != term:
                heredoc_body.append(lines[i])
                i += 1
            raw_end = min(i, len(lines) - 1)

        raw = "\n".join(lines[start_line - 1 : raw_end + 1])
        i += 1

        if keyword not in KNOWN_INSTRUCTIONS:
            continue

        flags, rest = _split_flags(value)
        json_form = _parse_json_form(rest) is not None
        if heredoc_body:
            # O corpo do heredoc é comando de verdade: precisa ser auditável.
            rest = rest + " " + " ".join(x.strip() for x in heredoc_body if x.strip())

        instructions.append(
            DockerInstruction(
                keyword=keyword,
                value=rest.strip(),
                flags=flags,
                start_line=start_line,
                end_line=raw_end + 1,
                raw=raw,
                json_form=json_form,
            )
        )

    return directives, instructions


def _parse_env_pairs(value: str) -> list[tuple[str, str]]:
    """`ENV A=1 B=2` (moderno) e `ENV A valor com espaco` (legado)."""
    tokens = _safe_shlex(value)
    if not tokens:
        return []
    if "=" in tokens[0]:
        pairs = []
        for tok in tokens:
            if "=" in tok:
                k, _, v = tok.partition("=")
                pairs.append((k, v))
        return pairs
    return [(tokens[0], " ".join(tokens[1:]))]


def parse_dockerfile(content: str, path: str) -> tuple[DockerfileSpec, list[Workload]]:
    directives, instructions = _tokenize(content)

    stages: list[DockerStage] = []
    known_stage_names: set[str] = set()

    for inst in instructions:
        if inst.keyword != "FROM":
            if stages:
                inst.stage_index = stages[-1].index
                stages[-1].instructions.append(inst)
            continue

        m = _FROM_RE.match(inst.value)
        image_raw = m.group("image") if m else inst.value
        stage_name = m.group("name") if m else None
        base = ImageRef.parse(image_raw, frozenset(known_stage_names))
        idx = len(stages)
        inst.stage_index = idx
        stages.append(
            DockerStage(
                index=idx,
                name=stage_name,
                base=base,
                start_line=inst.start_line,
                instructions=[inst],
            )
        )
        if stage_name:
            known_stage_names.add(stage_name.lower())

    if stages:
        stages[-1].is_final = True

    spec = DockerfileSpec(directives=directives, stages=stages, instructions=instructions)
    return spec, [_stage_to_workload(s, path) for s in stages]


def _stage_to_workload(stage: DockerStage, path: str) -> Workload:
    env: list[EnvVar] = []
    ports: list[PortBinding] = []
    mounts: list[VolumeMount] = []
    entrypoint: list[str] = []
    command: list[str] = []
    user: str | None = None
    probes: list[str] = []

    for inst in stage.instructions:
        loc = SourceLocation(file=path, start_line=inst.start_line, end_line=inst.end_line)

        if inst.keyword == "ENV":
            for k, v in _parse_env_pairs(inst.value):
                env.append(EnvVar(name=k, value=v, location=loc))

        elif inst.keyword == "EXPOSE":
            for tok in inst.value.split():
                port, _, proto = tok.partition("/")
                try:
                    ports.append(
                        PortBinding(
                            container_port=int(port), protocol=(proto or "tcp").lower(), raw=tok
                        )
                    )
                except ValueError:
                    # `EXPOSE $PORT` — não avaliável estaticamente.
                    ports.append(PortBinding(raw=tok))

        elif inst.keyword == "VOLUME":
            targets = _parse_json_form(inst.value) or _safe_shlex(inst.value)
            for t in targets:
                mounts.append(VolumeMount(target=t, type=MountType.VOLUME, raw=inst.value))

        elif inst.keyword == "USER":
            user = inst.value.split(":")[0].strip() or None

        elif inst.keyword == "ENTRYPOINT":
            entrypoint = _parse_json_form(inst.value) or _safe_shlex(inst.value)

        elif inst.keyword == "CMD":
            command = _parse_json_form(inst.value) or _safe_shlex(inst.value)

        elif inst.keyword == "HEALTHCHECK":
            if inst.value.strip().upper() != "NONE":
                probes.append("healthcheck")

    return Workload(
        name=stage.name or f"stage-{stage.index}",
        kind=WorkloadKind.BUILD_STAGE,
        location=SourceLocation(file=path, start_line=stage.start_line),
        image=stage.base,
        entrypoint=entrypoint,
        command=command,
        env=env,
        ports=ports,
        mounts=mounts,
        security=SecurityPosture(run_as_user=user),
        probes=probes,
        is_final_stage=stage.is_final,
    )
