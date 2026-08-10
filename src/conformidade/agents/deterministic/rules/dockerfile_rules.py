"""Regras específicas de Dockerfile.

Sobre `framework_refs`: são referências cruzadas informativas. O identificador
canônico — e a chave que o agente de recuperação usa no corpus — é sempre o
`control_id` (CONF-*). As citações a benchmarks externos precisam ser conferidas
contra a versão oficial antes de irem para um relatório de auditoria formal.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

from conformidade.agents.deterministic.models import (
    ArtifactKind,
    DockerInstruction,
    ParsedArtifact,
    Severity,
    SourceLocation,
)
from conformidade.agents.deterministic.rules.base import Observation, registry
from conformidade.agents.deterministic.rules.shared import (
    ROOT_USER_VALUES,
    detect_secret,
    redact,
)

DOCKERFILE_ONLY = (ArtifactKind.DOCKERFILE,)

_PIPE_TO_SHELL = re.compile(
    r"\b(curl|wget|fetch)\b[^|;&]*\|\s*(sudo\s+)?(ba|z|k|da)?sh\b|"
    r"\b(curl|wget)\b[^|;&]*\|\s*(sudo\s+)?(python[0-9.]*|perl|ruby|node)\b",
    re.IGNORECASE,
)
_SUDO = re.compile(r"(^|[\s;&|(])sudo\s+", re.IGNORECASE)
_CHMOD_WORLD_WRITABLE = re.compile(
    r"\bchmod\b[^;&|]*?(\s|-R\s|--recursive\s)*(0?777|0?666|a\+w|o\+w|ugo\+w)\b", re.IGNORECASE
)
_UPGRADE_ALONE = re.compile(
    r"\b(apt-get|apt)\s+(-[^\s]+\s+)*(upgrade|dist-upgrade)\b|"
    r"\byum\s+(-[^\s]+\s+)*(upgrade|update)\b(?!\s*-)|"
    r"\bapk\s+(-[^\s]+\s+)*upgrade\b|"
    r"\bdnf\s+(-[^\s]+\s+)*(upgrade|update)\b",
    re.IGNORECASE,
)
_APT_INSTALL = re.compile(r"\b(apt-get|apt)\s+(-[^\s]+\s+)*install\b", re.IGNORECASE)
_APT_CLEANUP = re.compile(r"rm\s+-rf?\s+[^\s;&|]*/var/lib/apt/lists|apt-get\s+clean", re.IGNORECASE)
_NO_RECOMMENDS = re.compile(r"--no-install-recommends", re.IGNORECASE)
_REMOTE_SRC = re.compile(r"^(https?|ftp)://", re.IGNORECASE)
_ARCHIVE_SUFFIX = re.compile(r"\.(tar|tar\.gz|tgz|tar\.bz2|tbz2|tar\.xz|txz|tar\.zst)$", re.I)


def _loc(artifact: ParsedArtifact, inst: DockerInstruction) -> SourceLocation:
    return SourceLocation(file=artifact.path, start_line=inst.start_line, end_line=inst.end_line)


def _instructions(artifact: ParsedArtifact, *keywords: str) -> Iterator[DockerInstruction]:
    if artifact.dockerfile is None:
        return
    wanted = {k.upper() for k in keywords}
    for inst in artifact.dockerfile.instructions:
        if not wanted or inst.keyword in wanted:
            yield inst


def _final_stage_instructions(artifact: ParsedArtifact) -> Iterator[DockerInstruction]:
    if artifact.dockerfile is None:
        return
    for stage in artifact.dockerfile.stages:
        if stage.is_final:
            yield from stage.instructions


def _first_line(text: str, limit: int = 160) -> str:
    single = " ".join(text.split())
    return single if len(single) <= limit else single[: limit - 1] + "…"


# --------------------------------------------------------------------------


@registry.register(
    control_id="CONF-DKR-001",
    title="Imagem final não declara usuário não-root",
    severity=Severity.HIGH,
    applies_to=DOCKERFILE_ONLY,
    rationale=(
        "Sem USER, o processo roda como root dentro do container. Combinado com uma "
        "fuga de container ou uma montagem de volume, root no container vira root no host."
    ),
    remediation="Crie um usuário dedicado e declare `USER <uid>` no último stage. "
    "Prefira UID numérico: o PodSecurityStandard `restricted` valida o UID, não o nome.",
    framework_refs=("CIS Docker Benchmark — 4.1",),
)
def rule_dockerfile_root_user(artifact: ParsedArtifact) -> Iterator[Observation]:
    final = [w for w in artifact.workloads if w.is_final_stage]
    if not final:
        return
    workload = final[0]
    user = workload.security.run_as_user

    if user is None:
        yield Observation(
            message=(
                "Nenhuma instrução USER no stage final: o container roda como root, "
                "a menos que a imagem base defina um usuário (o que não é verificável "
                "estaticamente a partir deste arquivo)."
            ),
            location=workload.location,
            target=workload.name,
            evidence=f"FROM {workload.image.raw if workload.image else '?'}",
        )
    elif user.lower() in ROOT_USER_VALUES:
        yield Observation(
            message=f"O stage final declara explicitamente `USER {user}`.",
            location=workload.location,
            target=workload.name,
            evidence=f"USER {user}",
        )


@registry.register(
    control_id="CONF-DKR-002",
    title="Imagem sem HEALTHCHECK",
    severity=Severity.LOW,
    applies_to=DOCKERFILE_ONLY,
    rationale="Sem healthcheck o orquestrador não distingue container vivo de container travado.",
    remediation="Adicione `HEALTHCHECK` ao stage final. Em Kubernetes as probes do "
    "manifesto prevalecem, mas o HEALTHCHECK ainda vale para execução local e Compose.",
    framework_refs=("CIS Docker Benchmark — 4.6",),
)
def rule_dockerfile_no_healthcheck(artifact: ParsedArtifact) -> Iterator[Observation]:
    final = [w for w in artifact.workloads if w.is_final_stage]
    if final and not final[0].probes:
        yield Observation(
            message="O stage final não declara HEALTHCHECK.",
            location=final[0].location,
            target=final[0].name,
        )


@registry.register(
    control_id="CONF-DKR-003",
    title="ADD usado onde COPY bastaria",
    severity=Severity.MEDIUM,
    applies_to=DOCKERFILE_ONLY,
    rationale="ADD tem comportamento implícito (extrai arquivos, baixa URLs). "
    "COPY faz só o que está escrito.",
    remediation="Troque `ADD` por `COPY` quando a origem for um arquivo local comum.",
    framework_refs=("CIS Docker Benchmark — 4.9",),
)
def rule_dockerfile_add_instead_of_copy(artifact: ParsedArtifact) -> Iterator[Observation]:
    for inst in _instructions(artifact, "ADD"):
        sources = inst.value.split()[:-1]
        if not sources:
            continue
        # ADD é legítimo para extrair tarball; só reporta o resto.
        if any(_REMOTE_SRC.match(s) or _ARCHIVE_SUFFIX.search(s) for s in sources):
            continue
        yield Observation(
            message="ADD com origem local comum; COPY é o equivalente sem efeito colateral.",
            location=_loc(artifact, inst),
            evidence=_first_line(inst.raw),
        )


@registry.register(
    control_id="CONF-DKR-004",
    title="ADD baixando conteúdo remoto durante o build",
    severity=Severity.HIGH,
    applies_to=DOCKERFILE_ONLY,
    rationale="Conteúdo remoto sem verificação de integridade entra na imagem. "
    "Se a origem for comprometida, o build importa o comprometimento silenciosamente.",
    remediation="Baixe em um stage de build com verificação de checksum/assinatura e "
    "copie o artefato verificado com COPY --from.",
    framework_refs=("CIS Docker Benchmark — 4.9",),
)
def rule_dockerfile_add_remote(artifact: ParsedArtifact) -> Iterator[Observation]:
    for inst in _instructions(artifact, "ADD"):
        for src in inst.value.split()[:-1]:
            if _REMOTE_SRC.match(src):
                yield Observation(
                    message=f"ADD busca `{src}` da rede durante o build, sem verificação.",
                    location=_loc(artifact, inst),
                    evidence=_first_line(inst.raw),
                )


@registry.register(
    control_id="CONF-DKR-005",
    title="Script remoto executado direto no shell",
    severity=Severity.HIGH,
    applies_to=DOCKERFILE_ONLY,
    rationale="`curl | sh` executa código arbitrário de terceiro em tempo de build, "
    "sem checksum e sem possibilidade de revisão.",
    remediation="Baixe o script, verifique o hash contra um valor fixado e só então execute.",
)
def rule_dockerfile_pipe_to_shell(artifact: ParsedArtifact) -> Iterator[Observation]:
    for inst in _instructions(artifact, "RUN"):
        if _PIPE_TO_SHELL.search(inst.value):
            yield Observation(
                message="RUN encadeia download da rede diretamente em um interpretador.",
                location=_loc(artifact, inst),
                evidence=_first_line(inst.value),
            )


@registry.register(
    control_id="CONF-DKR-006",
    title="Atualização de pacotes do sistema dentro do build",
    severity=Severity.MEDIUM,
    applies_to=DOCKERFILE_ONLY,
    rationale="`apt-get upgrade` produz builds não reprodutíveis: a mesma Dockerfile "
    "gera imagens diferentes conforme o dia. Atualização é responsabilidade da imagem base.",
    remediation="Remova o upgrade e atualize a tag/digest da imagem base.",
    framework_refs=("CIS Docker Benchmark — 4.7",),
)
def rule_dockerfile_upgrade(artifact: ParsedArtifact) -> Iterator[Observation]:
    for inst in _instructions(artifact, "RUN"):
        m = _UPGRADE_ALONE.search(inst.value)
        if m:
            yield Observation(
                message=f"RUN executa `{m.group(0).strip()}`, tornando o build não reprodutível.",
                location=_loc(artifact, inst),
                evidence=_first_line(inst.value),
            )


@registry.register(
    control_id="CONF-DKR-007",
    title="Uso de sudo dentro da imagem",
    severity=Severity.MEDIUM,
    applies_to=DOCKERFILE_ONLY,
    rationale="O build já roda como root; sudo é desnecessário e, se o binário ficar "
    "na imagem final, vira caminho de escalada para o processo da aplicação.",
    remediation="Remova o sudo. Use `USER root` temporariamente no build se precisar "
    "trocar de usuário.",
)
def rule_dockerfile_sudo(artifact: ParsedArtifact) -> Iterator[Observation]:
    for inst in _instructions(artifact, "RUN"):
        if _SUDO.search(inst.value):
            yield Observation(
                message="RUN usa sudo.",
                location=_loc(artifact, inst),
                evidence=_first_line(inst.value),
            )


@registry.register(
    control_id="CONF-DKR-008",
    title="Permissão de escrita para todos",
    severity=Severity.MEDIUM,
    applies_to=DOCKERFILE_ONLY,
    rationale="Arquivo gravável por qualquer usuário permite que um processo comprometido "
    "sobrescreva binários ou configuração da própria aplicação.",
    remediation="Use a permissão mínima necessária e `COPY --chown` para ajustar dono.",
)
def rule_dockerfile_world_writable(artifact: ParsedArtifact) -> Iterator[Observation]:
    for inst in _instructions(artifact, "RUN"):
        m = _CHMOD_WORLD_WRITABLE.search(inst.value)
        if m:
            yield Observation(
                message=f"RUN concede escrita irrestrita (`{m.group(0).strip()}`).",
                location=_loc(artifact, inst),
                evidence=_first_line(inst.value),
            )


@registry.register(
    control_id="CONF-DKR-009",
    title="Cache do gerenciador de pacotes não removido",
    severity=Severity.LOW,
    applies_to=DOCKERFILE_ONLY,
    rationale="O cache incha a imagem e aumenta a superfície analisada por scanners.",
    remediation="Encerre o mesmo RUN com `rm -rf /var/lib/apt/lists/*`.",
)
def rule_dockerfile_apt_cache(artifact: ParsedArtifact) -> Iterator[Observation]:
    for inst in _instructions(artifact, "RUN"):
        if _APT_INSTALL.search(inst.value) and not _APT_CLEANUP.search(inst.value):
            yield Observation(
                message="RUN instala pacotes sem limpar o cache do apt no mesmo layer.",
                location=_loc(artifact, inst),
                evidence=_first_line(inst.value),
            )


@registry.register(
    control_id="CONF-DKR-010",
    title="Instalação de pacotes recomendados desnecessários",
    severity=Severity.LOW,
    applies_to=DOCKERFILE_ONLY,
    rationale="Pacotes recomendados entram sem serem pedidos e ampliam a superfície de ataque.",
    remediation="Adicione `--no-install-recommends` ao apt-get install.",
    framework_refs=("CIS Docker Benchmark — 4.3",),
)
def rule_dockerfile_no_recommends(artifact: ParsedArtifact) -> Iterator[Observation]:
    for inst in _instructions(artifact, "RUN"):
        if _APT_INSTALL.search(inst.value) and not _NO_RECOMMENDS.search(inst.value):
            yield Observation(
                message="apt-get install sem `--no-install-recommends`.",
                location=_loc(artifact, inst),
                evidence=_first_line(inst.value),
            )


@registry.register(
    control_id="CONF-DKR-011",
    title="Cópia do contexto de build inteiro",
    severity=Severity.MEDIUM,
    applies_to=DOCKERFILE_ONLY,
    rationale="`COPY . .` leva para a imagem tudo que o .dockerignore não barrar — "
    "incluindo .env, .git e chaves que estejam no diretório.",
    remediation="Copie caminhos explícitos e mantenha um .dockerignore restritivo.",
    framework_refs=("CIS Docker Benchmark — 4.10",),
)
def rule_dockerfile_copy_context(artifact: ParsedArtifact) -> Iterator[Observation]:
    for inst in _instructions(artifact, "COPY", "ADD"):
        tokens = inst.value.split()
        if len(tokens) < 2:
            continue
        if any(src in (".", "./") for src in tokens[:-1]):
            yield Observation(
                message="A instrução copia o contexto de build inteiro para a imagem.",
                location=_loc(artifact, inst),
                evidence=_first_line(inst.raw),
            )


@registry.register(
    control_id="CONF-DKR-012",
    title="Porta de SSH exposta pela imagem",
    severity=Severity.MEDIUM,
    applies_to=DOCKERFILE_ONLY,
    rationale="Container não deve ser acessado por SSH: quebra a imutabilidade e cria "
    "um canal de administração fora da auditoria do orquestrador.",
    remediation="Remova o EXPOSE 22 e o servidor SSH. Use `docker exec` / `kubectl exec`.",
)
def rule_dockerfile_ssh_port(artifact: ParsedArtifact) -> Iterator[Observation]:
    for inst in _instructions(artifact, "EXPOSE"):
        for tok in inst.value.split():
            if tok.partition("/")[0] == "22":
                yield Observation(
                    message="A imagem expõe a porta 22 (SSH).",
                    location=_loc(artifact, inst),
                    evidence=_first_line(inst.raw),
                )


@registry.register(
    control_id="CONF-DKR-013",
    title="ENTRYPOINT/CMD em forma shell impede o encerramento gracioso",
    severity=Severity.MEDIUM,
    applies_to=DOCKERFILE_ONLY,
    rationale=(
        "Na forma shell o processo vira filho de /bin/sh, que é o PID 1 e não repassa "
        "SIGTERM. No drain do Kubernetes o container é morto por SIGKILL após o "
        "terminationGracePeriod, cortando conexões em andamento."
    ),
    remediation='Use a forma exec: `ENTRYPOINT ["/app/bin/start"]`.',
)
def rule_dockerfile_shell_form_entrypoint(artifact: ParsedArtifact) -> Iterator[Observation]:
    for inst in _final_stage_instructions(artifact):
        if inst.keyword in ("ENTRYPOINT", "CMD") and not inst.json_form and inst.value:
            yield Observation(
                message=f"{inst.keyword} está na forma shell; o PID 1 será o shell.",
                location=_loc(artifact, inst),
                evidence=_first_line(inst.raw),
            )


@registry.register(
    control_id="CONF-DKR-014",
    title="Segredo literal em ENV ou ARG",
    severity=Severity.CRITICAL,
    applies_to=DOCKERFILE_ONLY,
    rationale=(
        "ENV e ARG ficam gravados nos metadados da imagem: qualquer pessoa com acesso "
        "à imagem lê o valor com `docker history`, mesmo que um layer posterior apague o arquivo."
    ),
    remediation="Use `RUN --mount=type=secret` no build e injete segredo em runtime via "
    "Key Vault ou secret do orquestrador.",
    framework_refs=("CIS Docker Benchmark — 4.10",),
)
def rule_dockerfile_secret_in_env(artifact: ParsedArtifact) -> Iterator[Observation]:
    for inst in _instructions(artifact, "ENV", "ARG"):
        for pair in inst.value.split():
            name, sep, value = pair.partition("=")
            if not sep:
                continue
            reason = detect_secret(name, value)
            if reason:
                yield Observation(
                    message=f"{inst.keyword} `{name}` — {reason}.",
                    location=_loc(artifact, inst),
                    evidence=f"{name}={redact(value)}",
                )


@registry.register(
    control_id="CONF-DKR-015",
    title="Instrução MAINTAINER descontinuada",
    severity=Severity.INFO,
    applies_to=DOCKERFILE_ONLY,
    rationale="MAINTAINER foi substituída por LABEL, que é consultável de forma padronizada.",
    remediation='Use `LABEL org.opencontainers.image.authors="..."`.',
)
def rule_dockerfile_maintainer(artifact: ParsedArtifact) -> Iterator[Observation]:
    for inst in _instructions(artifact, "MAINTAINER"):
        yield Observation(
            message="MAINTAINER está descontinuada.",
            location=_loc(artifact, inst),
            evidence=_first_line(inst.raw),
        )
