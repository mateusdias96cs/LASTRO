"""Consulta canônica em inglês, uma por controle.

Por que existe: o catálogo está em português e a documentação oficial está em
inglês. Buscar texto português contra corpus inglês degrada a recuperação. Como
as 36 consultas são fixas e conhecidas de antemão, elas são escritas à mão aqui
— não geradas por LLM em tempo de execução.

Isso preserva a propriedade da camada 1: mesmo controle → mesma consulta →
mesmo resultado. Reescrita de query com LLM tornaria o agente 2 não-determinístico
e impossível de testar por snapshot.

Cada consulta mistura de propósito dois registros:

* **termo técnico exato** (`allowPrivilegeEscalation`, `CAP_SYS_ADMIN`) — é o que
  a busca lexical casa, e é justamente onde embedding costuma falhar;
* **descrição conceitual** — é o que a busca densa casa quando a documentação
  usa outra redação.

O usuário nunca vê este texto: ele envia a configuração e recebe o relatório em
português.
"""

from __future__ import annotations

CONSULTAS: dict[str, str] = {
    # ------------------------------------------------------------ Dockerfile
    "CONF-DKR-001": (
        "Dockerfile USER instruction create non-root user for container image "
        "run as unprivileged user instead of root numeric UID"
    ),
    "CONF-DKR-002": (
        "Dockerfile HEALTHCHECK instruction container health status "
        "detect unhealthy container liveness"
    ),
    "CONF-DKR-003": (
        "Dockerfile use COPY instead of ADD instruction difference "
        "ADD implicit behavior tar extraction transparency"
    ),
    "CONF-DKR-004": (
        "Dockerfile ADD remote URL download during build integrity verification "
        "ADD --checksum supply chain risk of fetching remote files"
    ),
    "CONF-DKR-005": (
        "piping curl or wget output directly to shell in RUN instruction "
        "executing remote install script without checksum verification"
    ),
    "CONF-DKR-006": (
        "avoid apt-get upgrade dist-upgrade in Dockerfile non-reproducible build "
        "update base image instead of upgrading packages at build time"
    ),
    "CONF-DKR-007": (
        "sudo inside container image unnecessary build already runs as root "
        "privilege escalation path setuid binary in image"
    ),
    "CONF-DKR-008": (
        "chmod 777 world-writable file permissions in container image "
        "least privilege file ownership COPY --chown"
    ),
    "CONF-DKR-009": (
        "remove apt package manager cache /var/lib/apt/lists after install "
        "reduce image size same RUN layer cleanup"
    ),
    "CONF-DKR-010": (
        "apt-get install --no-install-recommends avoid unnecessary packages "
        "minimize installed packages attack surface"
    ),
    "CONF-DKR-011": (
        "COPY . copies entire build context into image dockerignore file "
        "prevent leaking .env .git credentials into image layers"
    ),
    "CONF-DKR-012": (
        "EXPOSE port 22 SSH server inside container anti-pattern "
        "use docker exec or kubectl exec instead of running sshd"
    ),
    "CONF-DKR-013": (
        "ENTRYPOINT CMD exec form versus shell form JSON array "
        "shell becomes PID 1 and does not forward SIGTERM graceful shutdown"
    ),
    "CONF-DKR-014": (
        "secret in Dockerfile ENV ARG stored in image metadata docker history "
        "use RUN --mount=type=secret build secrets not build args"
    ),
    "CONF-DKR-015": (
        "MAINTAINER instruction is deprecated in Dockerfile use LABEL instead "
        "org.opencontainers.image.authors annotation image metadata"
    ),
    # ------------------------------------------------- procedência da imagem
    "CONF-IMG-001": (
        "container image reference without tag defaults to latest "
        "always specify explicit image tag imagePullPolicy"
    ),
    "CONF-IMG-002": (
        "avoid latest tag mutable image tag different content per pull "
        "use immutable versioned tags for reproducible deployments"
    ),
    "CONF-IMG-003": (
        "pin container image by digest sha256 immutable content addressable "
        "image@sha256 instead of tag supply chain integrity"
    ),
    # ------------------------------ postura de runtime (Compose + Kubernetes)
    "CONF-WLD-001": (
        "privileged container disables isolation grants all capabilities and "
        "host device access container escape securityContext privileged true"
    ),
    "CONF-WLD-002": (
        "mounting docker socket /var/run/docker.sock inside container "
        "equivalent to root on host container escape containerd socket"
    ),
    "CONF-WLD-003": (
        "hostPath volume bind mount host directory /etc /proc /var/run into "
        "container breaks isolation read-only mount restriction"
    ),
    "CONF-WLD-004": (
        "hostNetwork hostPID hostIPC sharing host namespaces with container "
        "network_mode host see host processes sniff traffic"
    ),
    "CONF-WLD-005": (
        "Linux capabilities CAP_SYS_ADMIN CAP_NET_ADMIN CAP_SYS_PTRACE added to "
        "container cap_add dangerous capability container escape"
    ),
    "CONF-WLD-006": (
        "drop all Linux capabilities cap_drop ALL then add only required "
        "default capability set granted by container runtime"
    ),
    "CONF-WLD-007": (
        "container running as root user runAsNonRoot runAsUser non-zero UID "
        "user directive avoid uid 0 inside container"
    ),
    "CONF-WLD-008": (
        "readOnlyRootFilesystem read_only immutable container filesystem "
        "mount tmpfs for writable paths prevent writing binaries at runtime"
    ),
    "CONF-WLD-009": (
        "container CPU and memory resource limits requests noisy neighbor "
        "denial of service OOM limits deploy resources"
    ),
    "CONF-WLD-010": (
        "liveness readiness startup probe healthcheck container health "
        "orchestrator sends traffic to unhealthy container"
    ),
    "CONF-SEC-001": (
        "secret credential in environment variable visible in docker inspect "
        "kubectl describe use Secret object or secret manager instead of env"
    ),
    # --------------------------------------------------------------- Compose
    "CONF-CMP-001": (
        "no-new-privileges security_opt prevents setuid binary from gaining "
        "privileges NoNewPrivs flag Docker Compose"
    ),
    "CONF-CMP-002": (
        "publishing container port binds to all interfaces 0.0.0.0 instead of "
        "127.0.0.1 loopback exposing database port docker iptables bypass firewall"
    ),
    # ------------------------------------------------------------ Kubernetes
    "CONF-K8S-001": (
        "allowPrivilegeEscalation false securityContext setuid binary gaining "
        "additional privileges restricted pod security standard"
    ),
    "CONF-K8S-002": (
        "seccompProfile RuntimeDefault syscall filtering restrict kernel "
        "attack surface seccomp profile pod securityContext"
    ),
    "CONF-K8S-003": (
        "automountServiceAccountToken false service account token mounted into "
        "pod kubernetes API access from compromised container"
    ),
    "CONF-K8S-004": (
        "avoid default namespace dedicated namespace isolation RBAC "
        "NetworkPolicy workload separation"
    ),
    "CONF-K8S-005": (
        "hostPort maps container port directly on node bypasses Service and "
        "NetworkPolicy limits scheduling one pod per node"
    ),
}


def consulta_de(control_id: str) -> str:
    """Consulta canônica do controle. Erro explícito se faltar."""
    try:
        return CONSULTAS[control_id]
    except KeyError:
        raise KeyError(
            f"controle sem consulta de recuperação: {control_id}. "
            "Todo controle do catálogo precisa de uma entrada em CONSULTAS."
        ) from None
