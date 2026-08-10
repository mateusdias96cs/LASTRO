"""Parser de manifestos Kubernetes para o modelo normalizado.

Dois pontos que exigem cuidado e costumam ser feitos errado:

* o `securityContext` existe em dois níveis (pod e container) e o do container
  **sobrepõe** o do pod campo a campo — avaliar só um dos níveis produz tanto
  falso positivo quanto falso negativo;
* `volumeMounts` (no container) só diz o nome; o tipo real (hostPath, secret,
  emptyDir) está em `spec.volumes`. Sem cruzar os dois não dá para detectar
  montagem de caminho do host.
"""

from __future__ import annotations

from typing import Any

from conformidade.agents.deterministic.models import (
    EnvVar,
    ImageRef,
    K8sDocument,
    MountType,
    PortBinding,
    ResourceLimits,
    SecurityPosture,
    SourceLocation,
    VolumeMount,
    Workload,
    WorkloadKind,
)
from conformidade.agents.deterministic.parsers.yamlsrc import line_of, load_documents

WORKLOAD_KINDS = frozenset(
    {
        "Pod",
        "Deployment",
        "StatefulSet",
        "DaemonSet",
        "ReplicaSet",
        "ReplicationController",
        "Job",
        "CronJob",
    }
)

_VOLUME_TYPE_MAP = {
    "hostPath": MountType.HOST_PATH,
    "configMap": MountType.CONFIG_MAP,
    "secret": MountType.SECRET,
    "emptyDir": MountType.EMPTY_DIR,
    "projected": MountType.PROJECTED,
}


def _pod_spec(doc: dict[str, Any]) -> dict[str, Any] | None:
    """Desce até o PodSpec conforme o kind. CronJob tem dois níveis a mais."""
    kind = doc.get("kind")
    spec = doc.get("spec")
    if not isinstance(spec, dict):
        return None

    if kind == "Pod":
        return spec
    if kind == "CronJob":
        job = spec.get("jobTemplate")
        job_spec = job.get("spec") if isinstance(job, dict) else None
        template = job_spec.get("template") if isinstance(job_spec, dict) else None
    else:
        template = spec.get("template")

    if not isinstance(template, dict):
        return None
    pod = template.get("spec")
    return pod if isinstance(pod, dict) else None


def parse_kubernetes(
    content: str, path: str
) -> tuple[list[K8sDocument], list[Workload], list[str]]:
    docs, errors = load_documents(content)

    documents: list[K8sDocument] = []
    workloads: list[Workload] = []

    for index, doc in enumerate(docs):
        if not isinstance(doc, dict):
            errors.append(f"documento {index} não é um mapa YAML")
            continue

        meta = doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {}
        kind = doc.get("kind")
        name = meta.get("name")
        namespace = meta.get("namespace")
        loc = SourceLocation(
            file=path,
            start_line=line_of(doc, 1),
            pointer=f"[{index}].{kind or 'unknown'}",
        )

        pod = _pod_spec(doc) if kind in WORKLOAD_KINDS else None
        documents.append(
            K8sDocument(
                api_version=_str_or_none(doc.get("apiVersion")),
                kind=_str_or_none(kind),
                name=_str_or_none(name),
                namespace=_str_or_none(namespace),
                location=loc,
                is_workload=pod is not None,
            )
        )

        if pod is None:
            continue

        volumes_by_name = _index_volumes(pod)
        annotations = meta.get("annotations") if isinstance(meta.get("annotations"), dict) else {}

        for group, wkind in (
            ("containers", WorkloadKind.CONTAINER),
            ("initContainers", WorkloadKind.INIT_CONTAINER),
        ):
            for container in pod.get(group) or []:
                if not isinstance(container, dict):
                    continue
                workloads.append(
                    _container_to_workload(
                        container=container,
                        pod=pod,
                        wkind=wkind,
                        owner_kind=_str_or_none(kind),
                        owner_name=_str_or_none(name),
                        namespace=_str_or_none(namespace),
                        volumes_by_name=volumes_by_name,
                        annotations=annotations,
                        path=path,
                    )
                )

    return documents, workloads, errors


def _index_volumes(pod: dict[str, Any]) -> dict[str, tuple[MountType, str | None]]:
    """nome do volume -> (tipo, origem). Necessário para resolver volumeMounts."""
    out: dict[str, tuple[MountType, str | None]] = {}
    for vol in pod.get("volumes") or []:
        if not isinstance(vol, dict):
            continue
        vname = str(vol.get("name", ""))
        for key, mtype in _VOLUME_TYPE_MAP.items():
            if key in vol:
                body = vol[key]
                source = body.get("path") if isinstance(body, dict) else None
                out[vname] = (mtype, _str_or_none(source))
                break
        else:
            out[vname] = (MountType.OTHER, None)
    return out


def _merge_security(
    pod: dict[str, Any], container: dict[str, Any], annotations: dict[str, Any], cname: str
) -> SecurityPosture:
    pod_sc = pod.get("securityContext") if isinstance(pod.get("securityContext"), dict) else {}
    c_sc = (
        container.get("securityContext")
        if isinstance(container.get("securityContext"), dict)
        else {}
    )

    def pick(field: str) -> Any:
        # O container vence; só cai para o pod quando não declara o campo.
        return c_sc.get(field, pod_sc.get(field))

    caps = c_sc.get("capabilities") if isinstance(c_sc.get("capabilities"), dict) else {}

    seccomp = _seccomp_type(c_sc.get("seccompProfile")) or _seccomp_type(
        pod_sc.get("seccompProfile")
    )

    apparmor = None
    profile = pick("appArmorProfile")
    if isinstance(profile, dict):
        apparmor = _str_or_none(profile.get("type"))
    if apparmor is None:
        # Forma antiga, via anotação por container.
        key = f"container.apparmor.security.beta.kubernetes.io/{cname}"
        apparmor = _str_or_none(annotations.get(key))

    run_as_user = pick("runAsUser")
    return SecurityPosture(
        privileged=c_sc.get("privileged"),
        run_as_user=None if run_as_user is None else str(run_as_user),
        run_as_group=_str_or_none(pick("runAsGroup")),
        run_as_non_root=pick("runAsNonRoot"),
        read_only_root_fs=c_sc.get("readOnlyRootFilesystem"),
        allow_privilege_escalation=c_sc.get("allowPrivilegeEscalation"),
        cap_add=[str(c).upper() for c in (caps.get("add") or [])],
        cap_drop=[str(c).upper() for c in (caps.get("drop") or [])],
        host_network=pod.get("hostNetwork"),
        host_pid=pod.get("hostPID"),
        host_ipc=pod.get("hostIPC"),
        seccomp_profile=seccomp,
        apparmor_profile=apparmor,
    )


def _seccomp_type(value: Any) -> str | None:
    return _str_or_none(value.get("type")) if isinstance(value, dict) else None


def _container_to_workload(
    *,
    container: dict[str, Any],
    pod: dict[str, Any],
    wkind: WorkloadKind,
    owner_kind: str | None,
    owner_name: str | None,
    namespace: str | None,
    volumes_by_name: dict[str, tuple[MountType, str | None]],
    annotations: dict[str, Any],
    path: str,
) -> Workload:
    cname = str(container.get("name", "unnamed"))
    qualified = f"{owner_name or owner_kind or 'workload'}/{cname}"
    loc = SourceLocation(
        file=path,
        start_line=line_of(container),
        pointer=f"{owner_kind}.{owner_name}.{wkind.value}.{cname}",
    )

    env: list[EnvVar] = []
    for item in container.get("env") or []:
        if not isinstance(item, dict):
            continue
        env.append(
            EnvVar(
                name=str(item.get("name", "")),
                value=_str_or_none(item.get("value")),
                location=loc,
                from_reference="valueFrom" in item,
            )
        )

    ports: list[PortBinding] = []
    for item in container.get("ports") or []:
        if not isinstance(item, dict):
            continue
        ports.append(
            PortBinding(
                container_port=_to_int(item.get("containerPort")),
                host_port=_to_int(item.get("hostPort")),
                protocol=str(item.get("protocol", "TCP")).lower(),
                raw=str(item.get("name") or item.get("containerPort")),
            )
        )

    mounts: list[VolumeMount] = []
    for item in container.get("volumeMounts") or []:
        if not isinstance(item, dict):
            continue
        vname = str(item.get("name", ""))
        mtype, source = volumes_by_name.get(vname, (MountType.OTHER, None))
        mounts.append(
            VolumeMount(
                target=str(item.get("mountPath", "")),
                source=source or vname,
                type=mtype,
                read_only=item.get("readOnly"),
                raw=vname,
            )
        )

    res = container.get("resources") if isinstance(container.get("resources"), dict) else {}
    limits = res.get("limits") if isinstance(res.get("limits"), dict) else {}
    requests = res.get("requests") if isinstance(res.get("requests"), dict) else {}

    probes = [
        p.removesuffix("Probe")
        for p in ("livenessProbe", "readinessProbe", "startupProbe")
        if container.get(p)
    ]

    image_raw = container.get("image")
    return Workload(
        name=qualified,
        kind=wkind,
        location=loc,
        image=ImageRef.parse(str(image_raw)) if image_raw else None,
        command=[str(c) for c in (container.get("command") or [])],
        args=[str(a) for a in (container.get("args") or [])],
        env=env,
        ports=ports,
        mounts=mounts,
        security=_merge_security(pod, container, annotations, cname),
        resources=ResourceLimits(
            cpu_limit=_str_or_none(limits.get("cpu")),
            memory_limit=_str_or_none(limits.get("memory")),
            cpu_request=_str_or_none(requests.get("cpu")),
            memory_request=_str_or_none(requests.get("memory")),
        ),
        probes=probes,
        namespace=namespace,
        owner_kind=owner_kind,
        service_account=_str_or_none(pod.get("serviceAccountName") or pod.get("serviceAccount")),
        automount_sa_token=pod.get("automountServiceAccountToken"),
    )


def _str_or_none(value: Any) -> str | None:
    return None if value is None else str(value)


def _to_int(value: Any) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None
