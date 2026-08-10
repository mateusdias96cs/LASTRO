from conformidade.agents.deterministic.models import MountType
from conformidade.agents.deterministic.parsers.compose import parse_compose
from conformidade.agents.deterministic.parsers.kubernetes import parse_kubernetes

# ---------------------------------------------------------------- compose


def test_compose_resolve_merge_key():
    _, workloads, errors = parse_compose(
        "x-base: &base\n"
        "  restart: always\n"
        "services:\n"
        "  api:\n"
        "    <<: *base\n"
        "    image: nginx:1.0\n",
        "compose.yaml",
    )
    assert errors == []
    assert workloads[0].image is not None
    assert workloads[0].image.tag == "1.0"


def test_compose_formas_de_porta():
    _, workloads, _ = parse_compose(
        "services:\n"
        "  a:\n"
        "    image: x:1\n"
        "    ports:\n"
        '      - "8080"\n'
        '      - "9090:80"\n'
        '      - "127.0.0.1:5432:5432/tcp"\n'
        "      - target: 3000\n"
        "        published: 3001\n",
        "compose.yaml",
    )
    ports = workloads[0].ports
    assert (ports[0].container_port, ports[0].host_port) == (8080, None)
    assert (ports[1].host_port, ports[1].container_port) == (9090, 80)
    assert ports[2].host_ip == "127.0.0.1"
    assert (ports[3].host_port, ports[3].container_port) == (3001, 3000)


def test_compose_bind_versus_volume_nomeado():
    _, workloads, _ = parse_compose(
        "services:\n"
        "  a:\n"
        "    image: x:1\n"
        "    volumes:\n"
        "      - /etc:/host-etc:ro\n"
        "      - dados:/var/lib/dados\n",
        "compose.yaml",
    )
    bind, nomeado = workloads[0].mounts
    assert bind.type is MountType.BIND and bind.read_only is True
    # Origem sem barra é volume nomeado — não pode virar achado de host path.
    assert nomeado.type is MountType.VOLUME


def test_compose_security_opt_aceita_dois_pontos_e_igual():
    for sep in (":", "="):
        _, workloads, _ = parse_compose(
            "services:\n"
            "  a:\n"
            "    image: x:1\n"
            "    security_opt:\n"
            f"      - no-new-privileges{sep}true\n",
            "compose.yaml",
        )
        assert workloads[0].security.no_new_privileges is True, f"separador {sep!r}"


def test_compose_linha_do_servico():
    _, workloads, _ = parse_compose(
        "services:\n  primeiro:\n    image: x:1\n  segundo:\n    image: y:1\n", "compose.yaml"
    )
    assert workloads[0].location.start_line == 2
    assert workloads[1].location.start_line == 4


# ------------------------------------------------------------- kubernetes


def _pod(body: str) -> str:
    return f"apiVersion: v1\nkind: Pod\nmetadata:\n  name: p\nspec:\n{body}"


def test_k8s_container_sobrepoe_o_pod():
    _, workloads, _ = parse_kubernetes(
        _pod(
            "  securityContext:\n"
            "    runAsUser: 1000\n"
            "    runAsNonRoot: true\n"
            "  containers:\n"
            "    - name: c\n"
            "      image: x:1\n"
            "      securityContext:\n"
            "        runAsUser: 0\n"
        ),
        "pod.yaml",
    )
    sec = workloads[0].security
    assert sec.run_as_user == "0"  # o container vence
    assert sec.run_as_non_root is True  # herdado do pod, pois o container não declara


def test_k8s_resolve_tipo_do_volume():
    _, workloads, _ = parse_kubernetes(
        _pod(
            "  volumes:\n"
            "    - name: hp\n"
            "      hostPath:\n"
            "        path: /var/run/docker.sock\n"
            "    - name: vazio\n"
            "      emptyDir: {}\n"
            "  containers:\n"
            "    - name: c\n"
            "      image: x:1\n"
            "      volumeMounts:\n"
            "        - name: hp\n"
            "          mountPath: /sock\n"
            "        - name: vazio\n"
            "          mountPath: /tmp\n"
        ),
        "pod.yaml",
    )
    hp, vazio = workloads[0].mounts
    assert hp.type is MountType.HOST_PATH and hp.source == "/var/run/docker.sock"
    assert vazio.type is MountType.EMPTY_DIR


def test_k8s_cronjob_desce_dois_niveis():
    docs, workloads, _ = parse_kubernetes(
        "apiVersion: batch/v1\n"
        "kind: CronJob\n"
        "metadata:\n"
        "  name: cj\n"
        "spec:\n"
        "  schedule: '* * * * *'\n"
        "  jobTemplate:\n"
        "    spec:\n"
        "      template:\n"
        "        spec:\n"
        "          containers:\n"
        "            - name: tarefa\n"
        "              image: x:1\n",
        "cj.yaml",
    )
    assert docs[0].is_workload is True
    assert [w.name for w in workloads] == ["cj/tarefa"]


def test_k8s_init_container_classificado():
    _, workloads, _ = parse_kubernetes(
        _pod(
            "  initContainers:\n"
            "    - name: init\n"
            "      image: x:1\n"
            "  containers:\n"
            "    - name: app\n"
            "      image: y:1\n"
        ),
        "pod.yaml",
    )
    kinds = {w.name: w.kind.value for w in workloads}
    assert kinds == {"p/app": "container", "p/init": "init_container"}


def test_k8s_doc_invalido_no_meio_nao_zera_o_resto():
    docs, workloads, errors = parse_kubernetes(
        "apiVersion: v1\nkind: Pod\nmetadata:\n  name: bom\nspec:\n"
        "  containers:\n    - name: c\n      image: x:1\n"
        "---\n"
        "- isto\n- e uma lista\n",
        "multi.yaml",
    )
    assert len(workloads) == 1
    assert errors  # o documento ruim foi reportado, sem derrubar o bom


def test_k8s_nao_workload_e_marcado():
    docs, workloads, _ = parse_kubernetes(
        "apiVersion: v1\nkind: Service\nmetadata:\n  name: svc\nspec:\n  ports: []\n", "svc.yaml"
    )
    assert docs[0].is_workload is False
    assert workloads == []
