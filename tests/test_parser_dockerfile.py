from conformidade.agents.deterministic.parsers.dockerfile import parse_dockerfile


def _spec(text: str):
    return parse_dockerfile(text, "Dockerfile")[0]


def test_continuacao_com_comentario_no_meio():
    """Comentário dentro de uma continuação deve sumir sem quebrar a instrução."""
    spec = _spec(
        "FROM alpine\n"
        "RUN apt-get update && \\\n"
        "    # instala as dependencias\n"
        "    apt-get install -y curl\n"
    )
    runs = [i for i in spec.instructions if i.keyword == "RUN"]
    assert len(runs) == 1
    assert "apt-get update" in runs[0].value
    assert "apt-get install -y curl" in runs[0].value
    assert "instala as dependencias" not in runs[0].value


def test_diretiva_escape_muda_a_continuacao():
    """Com `# escape=\\``, a crase passa a ser o caractere de continuação e a
    barra invertida deixa de ser — parsear errado junta ou separa instruções."""
    spec = _spec("# escape=`\nFROM alpine\nRUN echo um `\n  && echo dois\n")
    assert spec.directives["escape"] == "`"
    runs = [i for i in spec.instructions if i.keyword == "RUN"]
    assert len(runs) == 1
    assert "echo dois" in runs[0].value


def test_heredoc_nao_vira_instrucao():
    spec = _spec(
        "FROM alpine\nRUN <<EOF\necho primeira\nCOPY nao-sou-instrucao /destino\nEOF\nUSER 1000\n"
    )
    keywords = [i.keyword for i in spec.instructions]
    assert keywords == ["FROM", "RUN", "USER"]
    assert "nao-sou-instrucao" in spec.instructions[1].value


def test_forma_json_versus_shell():
    spec = _spec('FROM alpine\nCMD ["echo", "oi"]\nENTRYPOINT /bin/sh -c oi\n')
    by_kw = {i.keyword: i for i in spec.instructions}
    assert by_kw["CMD"].json_form is True
    assert by_kw["ENTRYPOINT"].json_form is False


def test_flags_de_instrucao():
    spec = _spec("FROM alpine\nCOPY --from=builder --chown=10001:10001 /a /b\n")
    copy = [i for i in spec.instructions if i.keyword == "COPY"][0]
    assert copy.flags == {"from": "builder", "chown": "10001:10001"}
    assert copy.value == "/a /b"


def test_multistage_e_referencia_de_stage():
    spec, workloads = parse_dockerfile(
        "FROM python:3.12 AS builder\nRUN echo build\nFROM builder\nUSER 10001\n", "Dockerfile"
    )
    assert len(spec.stages) == 2
    assert spec.stages[0].name == "builder"
    assert spec.stages[0].base.is_stage_ref is False
    # `FROM builder` referencia o stage anterior, não uma imagem de registry.
    assert spec.stages[1].base.is_stage_ref is True
    assert spec.stages[1].is_final is True
    assert workloads[1].security.run_as_user == "10001"


def test_numeros_de_linha_preservados():
    spec = _spec("FROM alpine\n\n# comentario\nUSER 1000\n")
    user = [i for i in spec.instructions if i.keyword == "USER"][0]
    assert user.start_line == 4


def test_env_moderno_e_legado():
    _, workloads = parse_dockerfile(
        'FROM alpine\nENV A=1 B="dois tres"\nENV LEGADO valor com espaco\n', "Dockerfile"
    )
    env = {e.name: e.value for e in workloads[0].env}
    assert env == {"A": "1", "B": "dois tres", "LEGADO": "valor com espaco"}


def test_expose_com_protocolo():
    _, workloads = parse_dockerfile("FROM alpine\nEXPOSE 8080/tcp 22\n", "Dockerfile")
    portas = {(p.container_port, p.protocol) for p in workloads[0].ports}
    assert portas == {(8080, "tcp"), (22, "tcp")}


def test_healthcheck_none_nao_conta_como_probe():
    _, workloads = parse_dockerfile("FROM alpine\nHEALTHCHECK NONE\n", "Dockerfile")
    assert workloads[0].probes == []
