"""Parser de docker-compose para o modelo normalizado."""

from __future__ import annotations

from typing import Any

from conformidade.agents.deterministic.models import (
    ComposeSpec,
    EnvVar,
    ImageRef,
    MountType,
    PortBinding,
    ResourceLimits,
    SecurityPosture,
    SourceLocation,
    VolumeMount,
    Workload,
    WorkloadKind,
)
from conformidade.agents.deterministic.parsers.yamlsrc import key_line, line_of, load_documents


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _parse_port(entry: Any) -> PortBinding:
    """Formas aceitas: 8080, "8080", "8080:80", "127.0.0.1:8080:80/tcp" e a
    forma longa em dicionário."""
    if isinstance(entry, dict):
        return PortBinding(
            container_port=_to_int(entry.get("target")),
            host_port=_to_int(entry.get("published")),
            host_ip=entry.get("host_ip"),
            protocol=str(entry.get("protocol", "tcp")).lower(),
            raw=str(entry),
        )

    raw = str(entry)
    text, _, proto = raw.partition("/")
    segments = text.split(":")

    host_ip = host_port = container_port = None
    if len(segments) == 1:
        container_port = segments[0]
    elif len(segments) == 2:
        host_port, container_port = segments
    elif len(segments) >= 3:
        host_ip, host_port, container_port = segments[0], segments[1], segments[2]

    return PortBinding(
        container_port=_to_int(container_port),
        host_port=_to_int(host_port),
        host_ip=host_ip,
        protocol=(proto or "tcp").lower(),
        raw=raw,
    )


def _to_int(value: Any) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _parse_volume(entry: Any) -> VolumeMount:
    if isinstance(entry, dict):
        vtype = str(entry.get("type", "volume")).lower()
        return VolumeMount(
            target=str(entry.get("target", "")),
            source=entry.get("source"),
            type=MountType.BIND if vtype == "bind" else _mount_type(vtype),
            read_only=entry.get("read_only"),
            raw=str(entry),
        )

    raw = str(entry)
    parts = raw.split(":")
    if len(parts) == 1:
        return VolumeMount(target=parts[0], type=MountType.VOLUME, raw=raw)

    source, target = parts[0], parts[1]
    options = parts[2].split(",") if len(parts) > 2 else []
    # Origem começando com / ou . é bind mount do host; caso contrário é
    # volume nomeado — a distinção define se a regra de host path dispara.
    is_bind = source.startswith(("/", ".", "~"))
    return VolumeMount(
        target=target,
        source=source,
        type=MountType.BIND if is_bind else MountType.VOLUME,
        read_only="ro" in options,
        raw=raw,
    )


def _mount_type(value: str) -> MountType:
    try:
        return MountType(value)
    except ValueError:
        return MountType.OTHER


def _parse_env(raw: Any, loc: SourceLocation) -> list[EnvVar]:
    out: list[EnvVar] = []
    if isinstance(raw, dict):
        for k, v in raw.items():
            out.append(EnvVar(name=str(k), value=None if v is None else str(v), location=loc))
    else:
        for item in _as_list(raw):
            key, sep, val = str(item).partition("=")
            out.append(EnvVar(name=key, value=val if sep else None, location=loc))
    return out


def _parse_security_opt(values: list[Any]) -> tuple[bool | None, str | None, str | None]:
    """Devolve (no_new_privileges, seccomp, apparmor).

    As duas formas circulam na prática e precisam ser aceitas: o Compose
    documenta `no-new-privileges:true` (dois-pontos) e a CLI do Docker usa
    `no-new-privileges=true` (igual). Tratar só uma delas faz um serviço
    corretamente endurecido ser reportado como vulnerável.
    """
    nnp: bool | None = None
    seccomp: str | None = None
    apparmor: str | None = None

    for item in values:
        text = str(item).strip()
        # Separa no primeiro `=` ou `:`, o que vier antes.
        idx_eq, idx_colon = text.find("="), text.find(":")
        candidates = [i for i in (idx_eq, idx_colon) if i != -1]
        if candidates:
            split_at = min(candidates)
            key, val = text[:split_at], text[split_at + 1 :]
        else:
            key, val = text, ""

        key = key.strip().lower()
        val = val.strip()

        if key == "no-new-privileges":
            # Sem valor, a flag sozinha já significa habilitada.
            nnp = True if val == "" else val.lower() in ("true", "1", "yes")
        elif key == "seccomp":
            seccomp = val or None
        elif key == "apparmor":
            apparmor = val or None

    return nnp, seccomp, apparmor


def parse_compose(content: str, path: str) -> tuple[ComposeSpec, list[Workload], list[str]]:
    docs, errors = load_documents(content)
    if not docs or not isinstance(docs[0], dict):
        return ComposeSpec(), [], errors or ["arquivo compose sem conteúdo utilizável"]

    root = docs[0]
    services = root.get("services") or {}
    if not isinstance(services, dict):
        return ComposeSpec(), [], errors + ["`services` não é um mapa"]

    workloads: list[Workload] = []
    for name, svc in services.items():
        if not isinstance(svc, dict):
            errors.append(f"serviço `{name}` não é um mapa")
            continue
        # A linha da chave (o nome do serviço), não a do primeiro campo dele.
        declared_at = key_line(services, str(name), line_of(svc))
        workloads.append(_service_to_workload(str(name), svc, path, declared_at))

    spec = ComposeSpec(
        version=str(root["version"]) if "version" in root else None,
        service_names=[str(k) for k in services],
        volume_names=[str(k) for k in (root.get("volumes") or {})],
        network_names=[str(k) for k in (root.get("networks") or {})],
        secret_names=[str(k) for k in (root.get("secrets") or {})],
    )
    return spec, workloads, errors


def _service_to_workload(
    name: str, svc: dict[str, Any], path: str, declared_at: int | None = None
) -> Workload:
    loc = SourceLocation(
        file=path, start_line=declared_at or line_of(svc), pointer=f"services.{name}"
    )

    nnp, seccomp, apparmor = _parse_security_opt(_as_list(svc.get("security_opt")))

    network_mode = str(svc.get("network_mode", "")).lower()
    security = SecurityPosture(
        privileged=svc.get("privileged"),
        run_as_user=str(svc["user"]).split(":")[0] if svc.get("user") is not None else None,
        read_only_root_fs=svc.get("read_only"),
        no_new_privileges=nnp,
        cap_add=[str(c).upper() for c in _as_list(svc.get("cap_add"))],
        cap_drop=[str(c).upper() for c in _as_list(svc.get("cap_drop"))],
        host_network=True if network_mode == "host" else None,
        host_pid=True if str(svc.get("pid", "")).lower() == "host" else None,
        host_ipc=True if str(svc.get("ipc", "")).lower() == "host" else None,
        seccomp_profile=seccomp,
        apparmor_profile=apparmor,
    )

    # Limites podem vir do formato v2 (mem_limit/cpus) ou do bloco deploy do v3.
    deploy = svc.get("deploy") or {}
    dep_res = deploy.get("resources") or {} if isinstance(deploy, dict) else {}
    limits = dep_res.get("limits") or {} if isinstance(dep_res, dict) else {}
    requests = dep_res.get("reservations") or {} if isinstance(dep_res, dict) else {}
    resources = ResourceLimits(
        cpu_limit=_str_or_none(limits.get("cpus") or svc.get("cpus")),
        memory_limit=_str_or_none(limits.get("memory") or svc.get("mem_limit")),
        cpu_request=_str_or_none(requests.get("cpus")),
        memory_request=_str_or_none(requests.get("memory")),
    )

    healthcheck = svc.get("healthcheck") or {}
    has_probe = bool(healthcheck) and not (
        isinstance(healthcheck, dict) and healthcheck.get("disable") is True
    )

    image_raw = svc.get("image")
    return Workload(
        name=name,
        kind=WorkloadKind.COMPOSE_SERVICE,
        location=loc,
        image=ImageRef.parse(str(image_raw)) if image_raw else None,
        entrypoint=_command_list(svc.get("entrypoint")),
        command=_command_list(svc.get("command")),
        env=_parse_env(svc.get("environment"), loc),
        ports=[_parse_port(p) for p in _as_list(svc.get("ports"))],
        mounts=[_parse_volume(v) for v in _as_list(svc.get("volumes"))],
        security=security,
        resources=resources,
        probes=["healthcheck"] if has_probe else [],
    )


def _str_or_none(value: Any) -> str | None:
    return None if value is None else str(value)


def _command_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    return str(value).split()
