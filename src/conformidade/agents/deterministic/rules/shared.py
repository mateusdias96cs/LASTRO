"""Vocabulário compartilhado pelas regras: caminhos sensíveis, capabilities de
alto risco e detecção de segredo literal."""

from __future__ import annotations

import re

# Caminhos do host cuja montagem no container quebra o isolamento.
SENSITIVE_HOST_PATHS: tuple[str, ...] = (
    "/",
    "/etc",
    "/proc",
    "/sys",
    "/dev",
    "/boot",
    "/root",
    "/home",
    "/usr",
    "/bin",
    "/sbin",
    "/lib",
    "/var/lib/docker",
    "/var/lib/kubelet",
    "/var/run",
    "/run",
)

DOCKER_SOCKET_PATHS: tuple[str, ...] = (
    "/var/run/docker.sock",
    "/run/docker.sock",
    "/var/run/containerd/containerd.sock",
    "/run/containerd/containerd.sock",
    "/var/run/crio/crio.sock",
)

# Capabilities que, sozinhas, permitem escapar do container ou comprometer o host.
HIGH_RISK_CAPABILITIES: frozenset[str] = frozenset(
    {
        "ALL",
        "SYS_ADMIN",
        "SYS_MODULE",
        "SYS_RAWIO",
        "SYS_PTRACE",
        "SYS_BOOT",
        "SYS_TIME",
        "NET_ADMIN",
        "DAC_READ_SEARCH",
        "DAC_OVERRIDE",
        "BPF",
        "PERFMON",
        "MKNOD",
    }
)

ROOT_USER_VALUES: frozenset[str] = frozenset({"0", "root"})


def is_sensitive_host_path(path: str | None) -> str | None:
    """Devolve o caminho sensível casado, ou None."""
    if not path:
        return None
    normalized = path.rstrip("/") or "/"
    for sensitive in SENSITIVE_HOST_PATHS:
        if normalized == sensitive or normalized.startswith(sensitive.rstrip("/") + "/"):
            # `/` casa com tudo; só reporta quando é exatamente a raiz.
            if sensitive == "/" and normalized != "/":
                continue
            return sensitive
    return None


def is_container_socket(path: str | None) -> bool:
    if not path:
        return False
    return path.rstrip("/") in DOCKER_SOCKET_PATHS


# --------------------------------------------------------------------------
# Segredos
# --------------------------------------------------------------------------

_SECRET_NAME_RE = re.compile(
    r"(PASSWORD|PASSWD|SECRET|TOKEN|API_?KEY|ACCESS_?KEY|PRIVATE_?KEY|CREDENTIAL"
    r"|CONNECTION_?STRING|CLIENT_?SECRET|AUTH|SESSION_?KEY|ENCRYPTION_?KEY)",
    re.IGNORECASE,
)

# Nomes que casam com o padrão acima mas apontam para um segredo em vez de contê-lo.
_SECRET_NAME_ALLOWLIST = re.compile(
    r"(_FILE$|_PATH$|_URI$|_ENDPOINT$|_NAME$|_ID$|_ENABLED$|_REQUIRED$|_TTL$|_EXPIRY$)",
    re.IGNORECASE,
)

_SECRET_VALUE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("chave de acesso AWS", re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("chave privada PEM", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("token do GitHub", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("chave da OpenAI", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    ("JSON Web Token", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.")),
    (
        "connection string com senha",
        re.compile(r"[a-zA-Z][a-zA-Z0-9+.-]*://[^:/\s]+:[^@/\s]{4,}@"),
    ),
)

# Valores que são referência a serem resolvidas em runtime, não o segredo em si.
_INTERPOLATION_RE = re.compile(r"^\$\{?[A-Za-z_][A-Za-z0-9_]*\}?$|^\{\{.*\}\}$")


def redact(value: str, keep: int = 3) -> str:
    """Nunca devolver o segredo no relatório — só o suficiente para localizá-lo."""
    if len(value) <= keep:
        return "*" * len(value)
    return value[:keep] + "*" * min(len(value) - keep, 12)


def detect_secret(name: str, value: str | None) -> str | None:
    """Devolve o motivo da suspeita, ou None.

    Duas vias independentes: nome suspeito com valor literal, ou valor que casa
    com o formato de uma credencial conhecida (aí o nome não importa).
    """
    if value is not None:
        for label, pattern in _SECRET_VALUE_PATTERNS:
            if pattern.search(value):
                return f"valor com formato de {label}"

    if not value or not value.strip():
        return None
    if _INTERPOLATION_RE.match(value.strip()):
        return None
    if _SECRET_NAME_ALLOWLIST.search(name):
        return None
    if _SECRET_NAME_RE.search(name):
        return "nome sugere credencial e o valor está literal no arquivo"
    return None
