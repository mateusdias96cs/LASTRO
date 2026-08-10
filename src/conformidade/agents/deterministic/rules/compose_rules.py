"""Regras específicas de docker-compose.

Só entra aqui o que não tem equivalente direto nos outros formatos — o resto
está em `workload_rules`, escrito uma vez para os três.
"""

from __future__ import annotations

from collections.abc import Iterator

from conformidade.agents.deterministic.models import ArtifactKind, ParsedArtifact, Severity
from conformidade.agents.deterministic.rules.base import Observation, registry

COMPOSE_ONLY = (ArtifactKind.DOCKER_COMPOSE,)

# Portas de serviços de dados e administração: publicá-las em todas as
# interfaces expõe o serviço para além da máquina, quase sempre sem querer.
SENSITIVE_SERVICE_PORTS: dict[int, str] = {
    22: "SSH",
    2375: "API do Docker (sem TLS)",
    2376: "API do Docker",
    3306: "MySQL/MariaDB",
    5432: "PostgreSQL",
    5672: "RabbitMQ",
    6379: "Redis",
    7000: "Cassandra",
    8086: "InfluxDB",
    9042: "Cassandra",
    9092: "Kafka",
    9200: "Elasticsearch",
    11211: "Memcached",
    15672: "RabbitMQ (painel)",
    27017: "MongoDB",
}


@registry.register(
    control_id="CONF-CMP-001",
    title="Escalada de privilégio não bloqueada",
    severity=Severity.MEDIUM,
    applies_to=COMPOSE_ONLY,
    rationale=(
        "Sem `no-new-privileges`, um binário com setuid dentro do container permite "
        "que o processo ganhe privilégios que não tinha ao iniciar."
    ),
    remediation='Adicione `security_opt: ["no-new-privileges:true"]` ao serviço.',
    framework_refs=("CIS Docker Benchmark — 5.25",),
)
def rule_compose_no_new_privileges(artifact: ParsedArtifact) -> Iterator[Observation]:
    for w in artifact.workloads:
        if w.security.no_new_privileges is not True:
            yield Observation(
                message="O serviço não declara `no-new-privileges`.",
                location=w.location,
                target=w.name,
                evidence="security_opt ausente ou sem no-new-privileges",
            )


@registry.register(
    control_id="CONF-CMP-002",
    title="Serviço de dados publicado em todas as interfaces",
    severity=Severity.HIGH,
    applies_to=COMPOSE_ONLY,
    rationale=(
        '`"5432:5432"` publica em 0.0.0.0, não em localhost. Em qualquer máquina com '
        "IP alcançável, o banco fica exposto na rede — e o firewall do host costuma "
        "ser contornado pelas regras que o Docker insere no iptables."
    ),
    remediation='Prefixe com o endereço de loopback (`"127.0.0.1:5432:5432"`) ou '
    "remova a publicação e use a rede interna do Compose.",
)
def rule_compose_exposed_data_port(artifact: ParsedArtifact) -> Iterator[Observation]:
    for w in artifact.workloads:
        for port in w.ports:
            if port.host_port is None:
                continue
            if port.host_ip not in (None, "", "0.0.0.0", "::"):
                continue
            service = SENSITIVE_SERVICE_PORTS.get(port.container_port or -1)
            if service:
                yield Observation(
                    message=(
                        f"Porta {port.host_port} ({service}) publicada em todas as "
                        "interfaces do host."
                    ),
                    location=w.location,
                    target=w.name,
                    evidence=port.raw or f"{port.host_port}:{port.container_port}",
                )
