"""Catálogo de correções — o trecho pronto para o usuário copiar.

## Por que isto é escrito à mão e não gerado

Configuração alucinada é pior que nenhuma configuração: o usuário cola no
cluster e o erro passa a ser nosso. O LLM da camada 3 explica **por que** o
achado importa; o que **fazer** sai daqui, de texto que nós escrevemos e que
está sob teste.

## Cobertura obrigatória

O catálogo da camada 1 declara, em `applies_to`, em quais formatos cada
controle pode disparar — 53 pares no total. Todo par precisa de uma correção,
e `tests/test_correcoes.py` falha se faltar uma. Sem essa checagem, um controle
novo entraria em produção detectando problema e não sabendo dizer como
resolvê-lo, o que é meio caminho.

O mesmo controle tem forma diferente em cada formato: `read_only: true` no
Compose e `readOnlyRootFilesystem: true` no Kubernetes são o mesmo controle e
trechos distintos. É por isso que a chave é o par, não o controle.

Os trechos são fragmentos para encaixar no arquivo do usuário, não manifestos
completos — `caminho` diz onde encaixar.
"""

from __future__ import annotations

from conformidade.agents.critic.contracts import (
    CatalogoDeCorrecoes,
    CorrecaoAplicavel,
    Formato,
)

_D = Formato.DOCKERFILE
_C = Formato.COMPOSE
_K = Formato.KUBERNETES


def _c(control_id: str, formato: Formato, trecho: str, explicacao: str, caminho: str = ""):
    return CorrecaoAplicavel(
        control_id=control_id,
        formato=formato,
        trecho=trecho.strip("\n"),
        explicacao=explicacao,
        caminho=caminho,
    )


CATALOGO = CatalogoDeCorrecoes(
    correcoes=(
        # ------------------------------------------------------- Compose puro
        _c(
            "CONF-CMP-001",
            _C,
            """
security_opt:
  - "no-new-privileges:true"
""",
            "Impede que um binário com setuid ganhe privilégios que o processo não tinha "
            "ao iniciar.",
            "services.<serviço>",
        ),
        _c(
            "CONF-CMP-002",
            _C,
            """
ports:
  - "127.0.0.1:5432:5432"
""",
            "Publica só no loopback. Sem o prefixo, o Docker abre a porta em 0.0.0.0 e "
            "insere regras no iptables que costumam contornar o firewall do host.",
            "services.<serviço>",
        ),
        # ---------------------------------------------------------- Dockerfile
        _c(
            "CONF-DKR-001",
            _D,
            """
RUN adduser --system --uid 10001 --no-create-home app
USER 10001
""",
            "UID numérico, não nome: o PodSecurityStandard `restricted` valida o número.",
            "último stage",
        ),
        _c(
            "CONF-DKR-002",
            _D,
            """
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \\
  CMD wget -qO- http://localhost:8080/health || exit 1
""",
            "Sem healthcheck o orquestrador não distingue container vivo de container travado.",
            "último stage",
        ),
        _c(
            "CONF-DKR-003",
            _D,
            "COPY app/ /app/",
            "`ADD` também extrai tarball e baixa URL. Para arquivo local comum, `COPY` faz "
            "só o que se espera.",
        ),
        _c(
            "CONF-DKR-004",
            _D,
            """
ADD --checksum=sha256:<digest> https://exemplo/arquivo.tar.gz /tmp/arquivo.tar.gz
""",
            "Sem checksum, o conteúdo baixado pode mudar entre builds sem que nada acuse.",
        ),
        _c(
            "CONF-DKR-005",
            _D,
            """
ADD --checksum=sha256:<digest> https://exemplo/install.sh /tmp/install.sh
RUN sh /tmp/install.sh && rm /tmp/install.sh
""",
            "Baixar e executar no mesmo pipe entrega a máquina de build a quem controlar a URL.",
        ),
        _c(
            "CONF-DKR-006",
            _D,
            """
FROM debian:12.5-slim@sha256:<digest>
""",
            "Atualize a imagem base em vez de rodar upgrade no build: upgrade torna o build "
            "não reprodutível, porque o resultado depende do dia.",
            "instrução FROM",
        ),
        _c(
            "CONF-DKR-007",
            _D,
            """
USER root
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates
USER 10001
""",
            "`sudo` dentro da imagem deixa um caminho de escalada em runtime. Troque de "
            "usuário no build, que é onde a permissão é realmente necessária.",
        ),
        _c(
            "CONF-DKR-008",
            _D,
            "COPY --chown=10001:10001 --chmod=640 config/ /app/config/",
            "Permissão de escrita para todos permite que qualquer processo do container "
            "altere o arquivo.",
        ),
        _c(
            "CONF-DKR-009",
            _D,
            """
RUN apt-get update \\
 && apt-get install -y --no-install-recommends curl \\
 && rm -rf /var/lib/apt/lists/*
""",
            "O `rm` precisa estar no MESMO `RUN`: em RUN separado o cache já virou camada e "
            "continua na imagem.",
        ),
        _c(
            "CONF-DKR-010",
            _D,
            "RUN apt-get install -y --no-install-recommends curl",
            "Sem a flag, o apt traz pacotes sugeridos e amplia a superfície da imagem.",
        ),
        _c(
            "CONF-DKR-011",
            _D,
            """
COPY pyproject.toml uv.lock ./
COPY src/ ./src/
""",
            "`COPY . .` leva `.git`, `.env` e credenciais para dentro da camada. Copie "
            "caminhos explícitos e mantenha um `.dockerignore` restritivo.",
        ),
        _c(
            "CONF-DKR-012",
            _D,
            "# EXPOSE 22 removido — use `docker exec` ou `kubectl exec` para acessar",
            "Servidor SSH no container adiciona um serviço de autenticação a manter e "
            "duplica o caminho de acesso que o runtime já oferece.",
        ),
        _c(
            "CONF-DKR-013",
            _D,
            'ENTRYPOINT ["/app/bin/start"]',
            "Na forma shell o processo vira filho do `/bin/sh`, que não repassa SIGTERM — "
            "o container morre por timeout em vez de encerrar graciosamente.",
        ),
        _c(
            "CONF-DKR-014",
            _D,
            """
RUN --mount=type=secret,id=token \\
    TOKEN="$(cat /run/secrets/token)" ./configurar.sh
""",
            "`ENV` e `ARG` ficam gravados na imagem e aparecem em `docker history`. O mount "
            "de segredo não vira camada.",
        ),
        _c(
            "CONF-DKR-015",
            _D,
            'LABEL org.opencontainers.image.authors="time@exemplo.com"',
            "`MAINTAINER` está descontinuado desde o Docker 1.13. O rótulo padronizado "
            "da OCI é lido por registries e ferramentas de inventário.",
        ),
        # ------------------------------------------------- imagem, três formatos
        _c(
            "CONF-IMG-001",
            _D,
            "FROM python:3.13-slim@sha256:<digest>",
            "Sem tag, o Docker assume `latest`, que muda sem aviso.",
            "instrução FROM",
        ),
        _c(
            "CONF-IMG-001",
            _C,
            'image: "python:3.13-slim@sha256:<digest>"',
            "Sem tag, o Compose assume `latest`, que muda sem aviso.",
            "services.<serviço>",
        ),
        _c(
            "CONF-IMG-001",
            _K,
            "image: python:3.13-slim@sha256:<digest>",
            "Sem tag, o kubelet assume `latest` e ainda muda a política de pull para Always.",
            "spec.containers[*]",
        ),
        _c(
            "CONF-IMG-002",
            _D,
            "FROM node:22.11.0-bookworm-slim@sha256:<digest>",
            "Tag móvel (`latest`, `stable`, `edge`) aponta para conteúdo diferente a cada "
            "pull — o build de hoje não reproduz o de ontem.",
            "instrução FROM",
        ),
        _c(
            "CONF-IMG-002",
            _C,
            'image: "node:22.11.0-bookworm-slim@sha256:<digest>"',
            "Tag móvel faz dois hosts subirem versões diferentes do mesmo serviço.",
            "services.<serviço>",
        ),
        _c(
            "CONF-IMG-002",
            _K,
            "image: node:22.11.0-bookworm-slim@sha256:<digest>",
            "Tag móvel faz réplicas do mesmo Deployment rodarem imagens diferentes conforme "
            "o nó onde caem.",
            "spec.containers[*]",
        ),
        _c(
            "CONF-IMG-003",
            _D,
            "FROM alpine:3.21@sha256:<digest>",
            "O digest é o único identificador imutável: a tag pode ser reapontada no registry.",
            "instrução FROM",
        ),
        _c(
            "CONF-IMG-003",
            _C,
            'image: "alpine:3.21@sha256:<digest>"',
            "O digest é o único identificador imutável: a tag pode ser reapontada no registry.",
            "services.<serviço>",
        ),
        _c(
            "CONF-IMG-003",
            _K,
            "image: alpine:3.21@sha256:<digest>",
            "O digest é o único identificador imutável: a tag pode ser reapontada no registry.",
            "spec.containers[*]",
        ),
        # ------------------------------------------------------ Kubernetes puro
        _c(
            "CONF-K8S-001",
            _K,
            """
securityContext:
  allowPrivilegeEscalation: false
""",
            "Bloqueia o ganho de privilégio por binário setuid dentro do container.",
            "spec.containers[*]",
        ),
        _c(
            "CONF-K8S-002",
            _K,
            """
securityContext:
  seccompProfile:
    type: RuntimeDefault
""",
            "Sem perfil declarado, o pod roda como `Unconfined` e nenhuma syscall é filtrada.",
            "spec (pod) ou spec.containers[*]",
        ),
        _c(
            "CONF-K8S-003",
            _K,
            "automountServiceAccountToken: false",
            "O token montado é credencial de acesso à API do cluster. Pod que não fala com a "
            "API não precisa dele.",
            "spec (pod)",
        ),
        _c(
            "CONF-K8S-004",
            _K,
            """
metadata:
  namespace: minha-aplicacao
""",
            "No namespace `default` a carga escapa de RBAC, NetworkPolicy, ResourceQuota e "
            "PodSecurity definidos por namespace.",
            "metadata",
        ),
        _c(
            "CONF-K8S-005",
            _K,
            """
# remova `hostPort` do container e exponha por Service
apiVersion: v1
kind: Service
metadata:
  name: minha-app
spec:
  selector:
    app: minha-app
  ports:
    - port: 80
      targetPort: 8080
""",
            "`hostPort` reserva a porta no nó, contorna o Service e limita o agendamento a um "
            "pod por nó.",
        ),
        # --------------------------------------------------------------- segredo
        _c(
            "CONF-SEC-001",
            _C,
            """
environment:
  POSTGRES_PASSWORD_FILE: /run/secrets/db_password
secrets:
  - db_password
""",
            "Segredo em `environment` vaza em `docker inspect`, nos logs e no arquivo "
            "versionado. O `_FILE` é lido do secret montado.",
            "services.<serviço>",
        ),
        _c(
            "CONF-SEC-001",
            _K,
            """
env:
  - name: POSTGRES_PASSWORD
    valueFrom:
      secretKeyRef:
        name: db-credenciais
        key: password
""",
            "Referência ao Secret em vez de valor literal. Em Azure, prefira o CSI driver do "
            "Key Vault com identidade gerenciada.",
            "spec.containers[*]",
        ),
        # ------------------------------------------------- carga: Compose e K8s
        _c(
            "CONF-WLD-001",
            _C,
            """
privileged: false
cap_add:
  - NET_ADMIN   # só a capability realmente necessária
devices:
  - "/dev/net/tun:/dev/net/tun"
""",
            "O modo privilegiado concede todas as capabilities e desativa seccomp e AppArmor. "
            "Conceda o device e a capability específicos.",
            "services.<serviço>",
        ),
        _c(
            "CONF-WLD-001",
            _K,
            """
securityContext:
  privileged: false
  capabilities:
    add: ["NET_ADMIN"]   # só a capability realmente necessária
""",
            "O modo privilegiado desativa a maior parte dos mecanismos de segurança do runtime.",
            "spec.containers[*]",
        ),
        _c(
            "CONF-WLD-002",
            _C,
            """
# remova a montagem do socket:
# volumes:
#   - /var/run/docker.sock:/var/run/docker.sock
""",
            "O socket do daemon equivale a root no host — mesmo montado como somente-leitura, "
            "a API permite criar container privilegiado.",
            "services.<serviço>.volumes",
        ),
        _c(
            "CONF-WLD-002",
            _K,
            """
# remova o volume do socket:
# volumes:
#   - name: docker-sock
#     hostPath:
#       path: /var/run/docker.sock
""",
            "Para build dentro do cluster, use uma solução sem daemon (Kaniko, BuildKit "
            "rootless) em vez de expor o socket.",
            "spec.volumes",
        ),
        _c(
            "CONF-WLD-003",
            _C,
            'volumes:\n  - "/var/log/app:/logs:ro"',
            "Monte o subdiretório específico e em modo somente-leitura, nunca a raiz do host.",
            "services.<serviço>",
        ),
        _c(
            "CONF-WLD-003",
            _K,
            """
volumes:
  - name: logs
    hostPath:
      path: /var/log/app
      type: Directory
# no container:
volumeMounts:
  - name: logs
    mountPath: /logs
    readOnly: true
""",
            "Subcaminho específico e `readOnly: true`. `hostPath` abre a fronteira de "
            "isolamento entre nó e container.",
            "spec.volumes e spec.containers[*].volumeMounts",
        ),
        _c(
            "CONF-WLD-004",
            _C,
            """
# remova estas linhas do serviço:
# network_mode: host
# pid: host
# ipc: host
""",
            "Compartilhar namespace do host entrega a pilha de rede, a lista de processos ou "
            "a memória compartilhada do nó.",
            "services.<serviço>",
        ),
        _c(
            "CONF-WLD-004",
            _K,
            """
spec:
  hostNetwork: false
  hostPID: false
  hostIPC: false
""",
            "Só DaemonSet de infraestrutura (CNI, coletor de log, agente de monitoração) "
            "justifica compartilhar namespace do nó.",
            "spec (pod)",
        ),
        _c(
            "CONF-WLD-005",
            _C,
            """
cap_drop:
  - ALL
cap_add:
  - CHOWN   # apenas a estritamente necessária
""",
            "`SYS_ADMIN`, `NET_ADMIN` e `SYS_PTRACE` permitem escapar do container. Descarte "
            "tudo e reconceda o mínimo.",
            "services.<serviço>",
        ),
        _c(
            "CONF-WLD-005",
            _K,
            """
securityContext:
  capabilities:
    drop: ["ALL"]
    add: ["NET_BIND_SERVICE"]   # apenas a estritamente necessária
""",
            "Capability de alto risco equivale, na prática, a privilégio de host.",
            "spec.containers[*]",
        ),
        _c(
            "CONF-WLD-006",
            _C,
            "cap_drop:\n  - ALL",
            "O runtime concede um conjunto padrão de capabilities que quase nenhuma aplicação "
            "usa. Descarte tudo e reconceda o que faltar.",
            "services.<serviço>",
        ),
        _c(
            "CONF-WLD-006",
            _K,
            """
securityContext:
  capabilities:
    drop: ["ALL"]
""",
            "Descartar todas as capabilities e reconceder só o necessário é exigência do "
            "PodSecurityStandard `restricted`, e a maioria das aplicações não precisa de "
            "nenhuma.",
            "spec.containers[*]",
        ),
        _c(
            "CONF-WLD-007",
            _C,
            'user: "10001:10001"',
            "Sem `user`, o processo roda como root dentro do container — e root no container "
            "vira root no host se houver fuga ou montagem de volume.",
            "services.<serviço>",
        ),
        _c(
            "CONF-WLD-007",
            _K,
            """
securityContext:
  runAsNonRoot: true
  runAsUser: 10001
  runAsGroup: 10001
""",
            "`runAsNonRoot: true` faz o kubelet recusar a imagem que tentar subir como root.",
            "spec (pod) ou spec.containers[*]",
        ),
        _c(
            "CONF-WLD-008",
            _C,
            """
read_only: true
tmpfs:
  - /tmp
""",
            "Raiz somente-leitura impede que um processo comprometido grave binário ou "
            "webshell. O `tmpfs` cobre os diretórios que realmente precisam de escrita.",
            "services.<serviço>",
        ),
        _c(
            "CONF-WLD-008",
            _K,
            """
securityContext:
  readOnlyRootFilesystem: true
# e no pod:
volumes:
  - name: tmp
    emptyDir: {}
volumeMounts:
  - name: tmp
    mountPath: /tmp
""",
            "Não confunda com volume montado somente-leitura: este campo trata da RAIZ do "
            "container, não de um volume.",
            "spec.containers[*]",
        ),
        _c(
            "CONF-WLD-009",
            _C,
            """
deploy:
  resources:
    limits:
      cpus: "1.0"
      memory: 512M
    reservations:
      cpus: "0.25"
      memory: 128M
""",
            "Sem limite, um container consome o nó inteiro e derruba os vizinhos.",
            "services.<serviço>",
        ),
        _c(
            "CONF-WLD-009",
            _K,
            """
resources:
  requests:
    cpu: 250m
    memory: 128Mi
  limits:
    cpu: "1"
    memory: 512Mi
""",
            "`requests` informa o escalonador; `limits` protege o nó. Declare os dois.",
            "spec.containers[*]",
        ),
        _c(
            "CONF-WLD-010",
            _C,
            """
healthcheck:
  test: ["CMD", "wget", "-qO-", "http://localhost:8080/health"]
  interval: 30s
  timeout: 3s
  retries: 3
  start_period: 5s
""",
            "Sem verificação, o Compose considera saudável qualquer container cujo processo "
            "não morreu.",
            "services.<serviço>",
        ),
        _c(
            "CONF-WLD-010",
            _K,
            """
livenessProbe:
  httpGet:
    path: /health
    port: 8080
  initialDelaySeconds: 10
  periodSeconds: 30
readinessProbe:
  httpGet:
    path: /ready
    port: 8080
  periodSeconds: 10
""",
            "`liveness` reinicia container travado; `readiness` tira do balanceamento quem "
            "ainda não está pronto. São coisas diferentes e as duas importam.",
            "spec.containers[*]",
        ),
    )
)

# `applies_to` da camada 1 usa outros rótulos. Um único ponto de tradução.
FORMATO_POR_APPLIES_TO = {
    "dockerfile": Formato.DOCKERFILE,
    "docker_compose": Formato.COMPOSE,
    "kubernetes": Formato.KUBERNETES,
}


def pares_obrigatorios() -> set[tuple[str, Formato]]:
    """Todo par (controle, formato) em que a camada 1 pode disparar."""
    from conformidade.agents.deterministic import list_controls

    return {
        (c.control_id, FORMATO_POR_APPLIES_TO[a])
        for c in list_controls()
        for a in c.applies_to
        if a in FORMATO_POR_APPLIES_TO
    }


def correcao_para(control_id: str, formato: Formato) -> CorrecaoAplicavel | None:
    return CATALOGO.para(control_id, formato)
