"""Aplica as correções no arquivo do usuário e devolve o arquivo inteiro.

## Por que o arquivo inteiro e não o trecho

Trecho pressupõe que quem lê sabe onde encaixar. Quem precisa desta ferramenta
normalmente não sabe — dizer "adicione em `spec.containers[*]`" para alguém que
nunca abriu um manifesto é o mesmo que não dizer nada.

## Por que o trecho do catálogo NÃO serve como patch

A primeira versão deste módulo parseava o trecho exibido e o fundia na
estrutura. O resultado, num compose real, foi:

    image: node:22.11.0-bookworm-slim@sha256:<digest>   # apagou a imagem do usuário
    cap_add: [NET_ADMIN]                                # concedeu capability que ele não pedia
    devices: ["/dev/net/tun:/dev/net/tun"]              # expôs um device do host

Os trechos do catálogo são **exemplos didáticos**. Aplicados literalmente,
destroem a configuração e em dois casos PIORAM a segurança. São coisas
diferentes: o trecho ensina, o patch conserta.

Daí a separação deste módulo:

* `PATCH` — alteração segura, que nunca inventa valor do usuário e nunca
  concede permissão. Só nega, remove ou define um padrão funcional;
* `MANUAL` — controle que não dá para aplicar sozinho. Fixar digest exige saber
  o digest real; healthcheck exige saber o endpoint da aplicação. Um valor
  inventado aqui deixaria o arquivo sintaticamente válido e funcionalmente
  quebrado, que é pior do que não mexer.

O relatório mostra os dois grupos, separados e com o motivo.
"""

from __future__ import annotations

import copy
import re
from typing import Any

import yaml

from conformidade.agents.critic.contracts import Formato
from conformidade.agents.deterministic import Finding

# ---------------------------------------------------------------------------
# Controles que exigem decisão humana. Aplicar um valor inventado deixaria o
# arquivo válido e quebrado.
# ---------------------------------------------------------------------------
MANUAL: dict[str, str] = {
    "CONF-IMG-001": "Só você sabe qual versão da imagem a aplicação precisa.",
    "CONF-IMG-002": "Trocar a tag móvel por uma versão fixa exige saber qual versão está em uso.",
    "CONF-IMG-003": "Fixar o digest exige consultar o registry: `docker buildx imagetools "
    "inspect <imagem>`.",
    "CONF-SEC-001": "Mover o segredo exige criar o secret no orquestrador ou no Key Vault.",
    "CONF-DKR-002": "O healthcheck precisa apontar para um endpoint que a sua aplicação responda.",
    "CONF-WLD-010": "A verificação de saúde precisa apontar para um endpoint que a sua "
    "aplicação responda.",
    "CONF-DKR-004": "Baixar com verificação exige o checksum publicado pelo fornecedor.",
    "CONF-DKR-005": "Verificar o script exige o hash publicado pelo fornecedor.",
    "CONF-DKR-006": "Atualizar a imagem base exige escolher a nova versão.",
    "CONF-DKR-011": "Quais caminhos copiar depende da estrutura do seu projeto.",
    "CONF-DKR-014": "Mover o segredo para o build exige configurar a origem dele.",
    "CONF-K8S-004": "Só você sabe em qual namespace esta carga deve rodar.",
}

# ---------------------------------------------------------------------------
# Patches seguros. Nunca concedem permissão; nunca sobrescrevem valor do
# usuário com exemplo.
# ---------------------------------------------------------------------------
PATCH_COMPOSE: dict[str, dict[str, Any]] = {
    "CONF-CMP-001": {"security_opt": ["no-new-privileges:true"]},
    "CONF-WLD-001": {"privileged": False},
    "CONF-WLD-006": {"cap_drop": ["ALL"]},
    "CONF-WLD-007": {"user": "10001:10001"},
    "CONF-WLD-008": {"read_only": True, "tmpfs": ["/tmp"]},
    "CONF-WLD-009": {
        "deploy": {"resources": {"limits": {"cpus": "1.0", "memory": "512M"}}},
    },
}

PATCH_K8S: dict[str, dict[str, Any]] = {
    # Nível do pod. `_alvo_kubernetes` já entrega o nó certo.
    "CONF-K8S-003": {"automountServiceAccountToken": False},
    "CONF-K8S-001": {"securityContext": {"allowPrivilegeEscalation": False}},
    "CONF-K8S-002": {"securityContext": {"seccompProfile": {"type": "RuntimeDefault"}}},
    "CONF-WLD-001": {"securityContext": {"privileged": False}},
    "CONF-WLD-006": {"securityContext": {"capabilities": {"drop": ["ALL"]}}},
    "CONF-WLD-007": {"securityContext": {"runAsNonRoot": True, "runAsUser": 10001}},
    "CONF-WLD-008": {"securityContext": {"readOnlyRootFilesystem": True}},
    "CONF-WLD-009": {
        "resources": {
            "requests": {"cpu": "250m", "memory": "128Mi"},
            "limits": {"cpu": "1", "memory": "512Mi"},
        }
    },
}

# Chaves a remover. `marca` restringe a remoção ao item que a contém.
REMOCOES: dict[str, tuple[tuple[str, str | None], ...]] = {
    "CONF-WLD-002": (("volumes", "docker.sock"),),
    "CONF-WLD-004": (
        ("network_mode", "host"),
        ("pid", "host"),
        ("ipc", "host"),
        ("hostNetwork", None),
        ("hostPID", None),
        ("hostIPC", None),
    ),
    # Capability de alto risco sai; nada é concedido em troca.
    "CONF-WLD-005": (("cap_add", None),),
    # `hostPort` sai; `containerPort` fica, senão o container perde a porta.
    # Publicar por Service é decisão de topologia e vai no relatório, não aqui.
    "CONF-K8S-005": (),
    "CONF-DKR-012": (),
}

# Capabilities que o CONF-WLD-005 remove do `securityContext` do Kubernetes.
_CAPS_PERIGOSAS = {"SYS_ADMIN", "NET_ADMIN", "SYS_PTRACE", "SYS_MODULE", "ALL"}


def descricao_do_reparo(control_id: str, formato: Formato) -> str:
    """O que de FATO foi alterado, derivado do patch.

    Não usa a explicação do catálogo: aquele texto descreve o exemplo
    didático, que é mais amplo que o patch. Para `privileged` o catálogo
    ensina a conceder o device específico, e o patch só define `false` —
    exibir o texto do catálogo na tabela de auditoria seria relatar uma
    alteração que não aconteceu.
    """
    partes: list[str] = []
    for chave, marca in REMOCOES.get(control_id, ()):
        partes.append(f"removeu `{chave}`" + (f" (`{marca}`)" if marca else ""))
    if control_id == "CONF-WLD-005":
        partes.append("removeu as capabilities de alto risco concedidas")
    if control_id == "CONF-CMP-002":
        partes.append("prefixou as portas publicadas com `127.0.0.1`, mantendo os números")
    if control_id == "CONF-K8S-005":
        partes.append("removeu `hostPort`, preservando `containerPort`")
    if control_id == "CONF-WLD-003":
        partes.append("acrescentou `:ro` à montagem do host")

    patches = PATCH_COMPOSE if formato is Formato.COMPOSE else PATCH_K8S
    if control_id in patches:
        partes.append("definiu " + ", ".join(f"`{c}`" for c in _chaves(patches[control_id])))
    if control_id in _DOCKERFILE_DESCRICAO:
        partes.append(_DOCKERFILE_DESCRICAO[control_id])
    return "; ".join(partes) or "sem alteração"


def _chaves(patch: dict[str, Any], prefixo: str = "") -> list[str]:
    saida: list[str] = []
    for chave, valor in patch.items():
        caminho = f"{prefixo}{chave}"
        if isinstance(valor, dict):
            saida += _chaves(valor, f"{caminho}.")
        elif isinstance(valor, bool):
            saida.append(f"{caminho}: {str(valor).lower()}")  # YAML usa true/false
        elif isinstance(valor, list):
            saida.append(caminho)
        else:
            saida.append(f"{caminho}: {valor}")
    return saida


_DOCKERFILE_DESCRICAO = {
    "CONF-DKR-001": "acrescentou um usuário sem privilégio e `USER 10001`",
    "CONF-DKR-003": "trocou `ADD` por `COPY` nas cópias locais",
    "CONF-DKR-010": "acrescentou `--no-install-recommends` ao apt-get",
    "CONF-DKR-012": "removeu o `EXPOSE 22`",
    "CONF-DKR-013": "converteu para a forma exec, preservando o comando",
    "CONF-DKR-015": "trocou `MAINTAINER` pelo rótulo da OCI, preservando o valor",
}


class Aplicacao:
    """Arquivo corrigido, mais o que foi feito e o que ficou para o usuário."""

    def __init__(
        self,
        conteudo: str,
        aplicados: list[str],
        manuais: dict[str, str],
        nao_aplicados: list[str],
    ) -> None:
        self.conteudo = conteudo
        self.aplicados = sorted(set(aplicados))
        self.manuais = manuais
        self.nao_aplicados = sorted(set(nao_aplicados))

    @property
    def mudou(self) -> bool:
        return bool(self.aplicados)


# --------------------------------------------------------------------- YAML


def _fundir(destino: dict[str, Any], patch: dict[str, Any]) -> None:
    """Merge profundo. Lista é substituída, não concatenada: somar `cap_drop`
    poderia manter uma entrada antiga contraditória."""
    for chave, valor in patch.items():
        if isinstance(valor, dict) and isinstance(destino.get(chave), dict):
            _fundir(destino[chave], valor)
        else:
            destino[chave] = copy.deepcopy(valor)


def _navegar(raiz: Any, pointer: str) -> Any:
    """Nunca cria caminho: se não existe, devolve `None` em vez de inventar
    estrutura no arquivo de outra pessoa."""
    atual = raiz
    for parte in filter(None, pointer.split(".")):
        if not isinstance(atual, dict) or parte not in atual:
            return None
        atual = atual[parte]
    return atual


# Onde mora o `podSpec` em cada tipo de recurso. Sem isto não há como sair do
# ponteiro lógico para o lugar real no YAML.
_CAMINHO_DO_POD = {
    "Pod": ("spec",),
    "Deployment": ("spec", "template", "spec"),
    "StatefulSet": ("spec", "template", "spec"),
    "DaemonSet": ("spec", "template", "spec"),
    "ReplicaSet": ("spec", "template", "spec"),
    "ReplicationController": ("spec", "template", "spec"),
    "Job": ("spec", "template", "spec"),
    "CronJob": ("spec", "jobTemplate", "spec", "template", "spec"),
}

# Controles que se corrigem no POD, não no container. O resto é do container.
_NO_NIVEL_DO_POD = frozenset(
    {
        "CONF-WLD-004",  # hostNetwork / hostPID / hostIPC
        "CONF-K8S-003",  # automountServiceAccountToken
    }
)


def _descer(no: Any, caminho: tuple[str, ...]) -> Any:
    for parte in caminho:
        if not isinstance(no, dict) or parte not in no:
            return None
        no = no[parte]
    return no


def _alvo_kubernetes(documentos: list[Any], pointer: str, control_id: str) -> Any:
    """Resolve o ponteiro LÓGICO da camada 1 para o nó real do YAML.

    A camada 1 emite `Deployment.loja-carrinho.container.carrinho`: tipo, nome
    do recurso, e nome do container. Isso não é um caminho de YAML — é uma
    identificação. Tratá-lo como caminho foi o bug que deixou o aplicador sem
    efeito nenhum em manifesto do Kubernetes, enquanto no Compose ele
    funcionava por coincidência, porque lá `services.api` é literalmente onde o
    serviço mora.

    Sintoma: catorze achados num Deployment, zero correções aplicadas, e nada
    no log — `_navegar` devolvia `None` e o achado ia silenciosamente para a
    lista de não aplicados.
    """
    partes = pointer.split(".")
    if len(partes) < 2:
        return None
    kind, nome = partes[0], partes[1]
    caminho_pod = _CAMINHO_DO_POD.get(kind)
    if caminho_pod is None:
        return None

    documento = next(
        (
            d
            for d in documentos
            if isinstance(d, dict)
            and d.get("kind") == kind
            and (d.get("metadata") or {}).get("name") == nome
        ),
        None,
    )
    if documento is None:
        return None

    if control_id == "CONF-K8S-004":  # namespace mora no metadata
        return documento.setdefault("metadata", {})

    pod = _descer(documento, caminho_pod)
    if not isinstance(pod, dict):
        return None
    if control_id in _NO_NIVEL_DO_POD:
        return pod

    # Container nomeado. `container` é literal no ponteiro, e o nome vem
    # depois — fatiar pela direita evita quebrar com nome que contenha ponto.
    if "container" not in partes:
        return pod
    nome_container = ".".join(partes[partes.index("container") + 1 :])
    containers = pod.get("containers")
    if not isinstance(containers, list):
        return None
    return next(
        (c for c in containers if isinstance(c, dict) and c.get("name") == nome_container),
        None,
    )


def _remover(alvo: dict[str, Any], control_id: str) -> bool:
    mexeu = False
    for chave, marca in REMOCOES.get(control_id, ()):
        if chave not in alvo:
            continue
        if marca is None:
            alvo.pop(chave)
            mexeu = True
        elif isinstance(alvo[chave], list):
            restante = [v for v in alvo[chave] if marca not in str(v)]
            if len(restante) != len(alvo[chave]):
                alvo[chave] = restante or None
                if alvo[chave] is None:
                    alvo.pop(chave)
                mexeu = True
        elif marca in str(alvo[chave]):
            alvo.pop(chave)
            mexeu = True

    # Kubernetes guarda as capabilities aninhadas.
    if control_id == "CONF-WLD-005":
        caps = alvo.get("securityContext", {}).get("capabilities", {})
        antes = list(caps.get("add", []))
        if antes:
            caps["add"] = [c for c in antes if str(c).upper() not in _CAPS_PERIGOSAS]
            if not caps["add"]:
                caps.pop("add")
            mexeu = mexeu or caps.get("add") != antes
    return mexeu


def _remover_hostport(alvo: dict[str, Any]) -> bool:
    """Tira só o `hostPort`, preservando `containerPort` e o nome.

    Apagar a entrada inteira de `ports` faria o container perder a porta que a
    aplicação escuta — conserto que quebra é pior que achado não corrigido.
    """
    portas = alvo.get("ports")
    if not isinstance(portas, list):
        return False
    mexeu = False
    for porta in portas:
        if isinstance(porta, dict) and "hostPort" in porta:
            porta.pop("hostPort")
            mexeu = True
    return mexeu


def _publicar_no_loopback(alvo: dict[str, Any]) -> bool:
    """Prefixa 127.0.0.1 nas portas publicadas, preservando as do usuário.

    Nunca troca a porta: reescrever `"5432:5432"` para um exemplo faria o
    serviço parar de responder onde a aplicação espera.
    """
    portas = alvo.get("ports")
    if not isinstance(portas, list):
        return False
    novas, mexeu = [], False
    for p in portas:
        texto = str(p)
        if re.match(r"^\d[\d.]*\.\d+:", texto) or texto.startswith("127.0.0.1:"):
            novas.append(p)
            continue
        if ":" in texto:
            novas.append(f"127.0.0.1:{texto}")
            mexeu = True
        else:
            novas.append(p)
    if mexeu:
        alvo["ports"] = novas
    return mexeu


def _somente_leitura_no_host(alvo: dict[str, Any]) -> bool:
    """Acrescenta `:ro` a montagem de caminho do host, sem trocar o caminho."""
    volumes = alvo.get("volumes")
    if not isinstance(volumes, list):
        return False
    novas, mexeu = [], False
    for v in volumes:
        texto = str(v)
        if texto.startswith("/") and texto.count(":") == 1:
            novas.append(f"{texto}:ro")
            mexeu = True
        else:
            novas.append(v)
    if mexeu:
        alvo["volumes"] = novas
    return mexeu


_ESPECIAIS = {
    "CONF-CMP-002": _publicar_no_loopback,
    "CONF-WLD-003": _somente_leitura_no_host,
    "CONF-K8S-005": _remover_hostport,
}


def _aplicar_yaml(conteudo: str, achados: list[Finding], formato: Formato) -> Aplicacao:
    documentos = list(yaml.safe_load_all(conteudo))
    patches = PATCH_COMPOSE if formato is Formato.COMPOSE else PATCH_K8S
    aplicados: list[str] = []
    manuais: dict[str, str] = {}
    nao: list[str] = []

    for achado in achados:
        cid = achado.control_id
        if cid in MANUAL:
            manuais[cid] = MANUAL[cid]
            continue

        pointer = (achado.location.pointer or "") if achado.location else ""
        if formato is Formato.KUBERNETES:
            alvo = _alvo_kubernetes(documentos, pointer, cid)
        else:
            alvo = None
            for doc in documentos:
                alvo = _navegar(doc, pointer)
                if isinstance(alvo, dict):
                    break

        if not isinstance(alvo, dict):
            nao.append(cid)
            continue

        mexeu = _remover(alvo, cid)
        if cid in _ESPECIAIS:
            mexeu = _ESPECIAIS[cid](alvo) or mexeu
        if cid in patches:
            _fundir(alvo, patches[cid])
            mexeu = True

        (aplicados if mexeu else nao).append(cid)

    texto = yaml.safe_dump_all(
        documentos, sort_keys=False, allow_unicode=True, default_flow_style=False
    )
    return Aplicacao(texto, aplicados, manuais, nao)


# --------------------------------------------------------------- Dockerfile


def _aplicar_dockerfile(conteudo: str, achados: list[Finding]) -> Aplicacao:
    linhas = conteudo.splitlines()
    aplicados: list[str] = []
    manuais: dict[str, str] = {}
    nao: list[str] = []

    def indice(prefixo: str) -> int | None:
        return next(
            (i for i, ln in enumerate(linhas) if ln.strip().upper().startswith(prefixo)), None
        )

    for achado in achados:
        cid = achado.control_id
        if cid in MANUAL:
            manuais[cid] = MANUAL[cid]
            continue

        if cid == "CONF-DKR-001":
            # UID numérico ao final. Não mexe em USER já existente.
            if indice("USER") is None:
                linhas += [
                    "",
                    "# CONF-DKR-001 — executa como usuário sem privilégio",
                    "RUN adduser --system --uid 10001 --no-create-home app || true",
                    "USER 10001",
                ]
                aplicados.append(cid)
            else:
                nao.append(cid)

        elif cid == "CONF-DKR-003":
            # `ADD origem local` → `COPY`, preservando os argumentos.
            trocou = False
            for i, ln in enumerate(linhas):
                if ln.strip().upper().startswith("ADD ") and "://" not in ln:
                    linhas[i] = re.sub(r"^(\s*)ADD\b", r"\1COPY", ln, flags=re.I)
                    trocou = True
            (aplicados if trocou else nao).append(cid)

        elif cid == "CONF-DKR-010":
            trocou = False
            for i, ln in enumerate(linhas):
                if "apt-get install" in ln and "--no-install-recommends" not in ln:
                    linhas[i] = ln.replace(
                        "apt-get install", "apt-get install --no-install-recommends", 1
                    )
                    trocou = True
            (aplicados if trocou else nao).append(cid)

        elif cid == "CONF-DKR-012":
            antes = len(linhas)
            linhas = [ln for ln in linhas if not re.match(r"^\s*EXPOSE\s+22\b", ln, re.I)]
            (aplicados if len(linhas) != antes else nao).append(cid)

        elif cid == "CONF-DKR-015":
            # Preserva o valor do MAINTAINER; só troca a instrução.
            i = indice("MAINTAINER")
            if i is not None:
                valor = linhas[i].split(None, 1)[1].strip().strip('"')
                linhas[i] = f'LABEL org.opencontainers.image.authors="{valor}"'
                aplicados.append(cid)
            else:
                nao.append(cid)

        elif cid == "CONF-DKR-013":
            # Forma shell → exec, preservando o comando do usuário.
            trocou = False
            for i, ln in enumerate(linhas):
                m = re.match(r"^(\s*)(ENTRYPOINT|CMD)\s+(?!\[)(.+)$", ln, re.I)
                if m:
                    partes = m.group(3).strip().split()
                    itens = ", ".join(f'"{p}"' for p in partes)
                    linhas[i] = f"{m.group(1)}{m.group(2).upper()} [{itens}]"
                    trocou = True
            (aplicados if trocou else nao).append(cid)

        else:
            nao.append(cid)

    return Aplicacao("\n".join(linhas).rstrip() + "\n", aplicados, manuais, nao)


# ------------------------------------------------------------------ entrada


def aplicar(conteudo: str, achados: list[Finding], formato: Formato) -> Aplicacao:
    """Devolve o arquivo do usuário com as correções seguras já dentro."""
    if formato is Formato.DOCKERFILE:
        return _aplicar_dockerfile(conteudo, achados)
    return _aplicar_yaml(conteudo, achados, formato)
