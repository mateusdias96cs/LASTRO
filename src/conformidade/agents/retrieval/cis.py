"""Mapa entre as recomendações do CIS Docker Benchmark e os controles daqui.

Por que existe: o CIS é a única fonte oficial do corpus escrita como
especificação de configuração — cada recomendação enuncia a norma e traz o
bloco `Remediation` com o valor correto. Para o gabarito da camada 2 saber que
`cis:docker-benchmark` é fonte relevante de um controle, alguém precisa
declarar qual recomendação corresponde a qual controle. Este módulo é essa
declaração.

## A disciplina que mantém isto honesto

O mapa foi escrito a partir do **título** de cada recomendação, antes de
qualquer medição, e não é ajustado depois de ver resultado. A tentação óbvia
seria mapear mais controles até o recall subir — e como declarar uma fonte
como relevante aumenta recall e nDCG **por construção**, o número subiria sem
que o sistema melhorasse. Mapear pelo resultado é envenenar o gabarito.

Pela mesma razão, o mapa é **conservador**: recomendação que apenas tangencia
um controle fica sem mapeamento. `4.2 trusted base images` e `4.12 signed
artifacts` são boas práticas reais e não enunciam nenhuma das nossas normas;
`5.23`/`5.24` tratam de `docker exec`, que é comando de operação e não aparece
em arquivo de configuração — que é a única entrada que o sistema recebe.

## Contra quebra silenciosa

`RECOMENDACOES` precisa corresponder **exatamente** ao que o extrator lê do
PDF, nos dois sentidos e por número e título literal. Se o CIS publicar uma
v1.9.0 que renumere ou reescreva um título, os testes em
`tests/test_cis_mapa.py` acusam a divergência em vez de o mapa virar ficção
silenciosa apontando para recomendação que não existe mais.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, field_validator, model_validator

# Documento ao qual este mapa se refere. Muda junto com o manifesto do corpus.
PAGE_ID = "cis:docker-benchmark"
VERSAO = "v1.8.0"

_NUMERO = re.compile(r"^[45]\.\d{1,2}$")


class RecomendacaoCIS(BaseModel):
    """Uma recomendação do CIS e os controles daqui que ela sustenta.

    `controles` vazio é válido e comum: a recomendação existe no documento, foi
    lida e conscientemente não mapeada. Registrar isso é melhor que omitir a
    linha, porque a omissão seria indistinguível de esquecimento.
    """

    numero: str
    titulo: str
    controles: tuple[str, ...] = ()

    @field_validator("numero")
    @classmethod
    def _numero_no_escopo(cls, v: str) -> str:
        if not _NUMERO.match(v):
            raise ValueError(
                f"`{v}` fora das seções 4 e 5 — só imagem/Dockerfile e runtime "
                "descrevem o que o usuário envia"
            )
        return v

    @field_validator("titulo")
    @classmethod
    def _titulo_e_literal(cls, v: str) -> str:
        # Título é chave de correspondência com o PDF. Espaço nas bordas ou
        # texto vazio quebraria a verificação sem produzir erro.
        if v != v.strip() or len(v) < 10:
            raise ValueError(f"título inválido ou não normalizado: {v!r}")
        return v

    @field_validator("controles")
    @classmethod
    def _controles_conhecidos(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        from conformidade.agents.retrieval.controls import DIRETORIO

        catalogo = {p.stem for p in DIRETORIO.glob("*.md")}
        desconhecidos = sorted(set(v) - catalogo)
        if desconhecidos:
            raise ValueError(f"control_id inexistente no catálogo: {desconhecidos}")
        if len(set(v)) != len(v):
            raise ValueError(f"control_id repetido em {v}")
        return v


class MapaCIS(BaseModel):
    recomendacoes: tuple[RecomendacaoCIS, ...]

    @model_validator(mode="after")
    def _sem_numero_repetido(self) -> MapaCIS:
        numeros = [r.numero for r in self.recomendacoes]
        repetidos = sorted({n for n in numeros if numeros.count(n) > 1})
        if repetidos:
            raise ValueError(f"recomendação declarada duas vezes: {repetidos}")
        return self

    def controles_cobertos(self) -> frozenset[str]:
        return frozenset(c for r in self.recomendacoes for c in r.controles)

    def por_controle(self, control_id: str) -> tuple[RecomendacaoCIS, ...]:
        return tuple(r for r in self.recomendacoes if control_id in r.controles)

    def numeros(self) -> frozenset[str]:
        return frozenset(r.numero for r in self.recomendacoes)


# --------------------------------------------------------------------------
# As 44 recomendações das seções 4 e 5, na ordem do documento.
#
# Mapeamento derivado do título. Comentário só onde a decisão não é óbvia.
# --------------------------------------------------------------------------

MAPA = MapaCIS(
    recomendacoes=(
        # ---------------- 4. Container Images and Build File Configuration
        RecomendacaoCIS(
            numero="4.1",
            titulo="Ensure that a user for the container has been created",
            # Cobre os dois lados do mesmo problema: declarar `USER` no
            # Dockerfile e o container não executar como root.
            controles=("CONF-DKR-001", "CONF-WLD-007"),
        ),
        RecomendacaoCIS(
            numero="4.2",
            titulo="Ensure that containers use only trusted base images",
            # Procedência de imagem. Não é fixação por tag nem por digest.
        ),
        RecomendacaoCIS(
            numero="4.3",
            titulo="Ensure that unnecessary packages are not installed in the container",
            controles=("CONF-DKR-010",),
        ),
        RecomendacaoCIS(
            numero="4.4",
            titulo="Ensure images are scanned and rebuilt to include security patches",
            # Processo de operação: escanear e reconstruir. O nosso controle
            # vizinho (CONF-DKR-006) é sobre atualizar pacotes DENTRO do build,
            # que é a 4.7.
        ),
        RecomendacaoCIS(
            numero="4.5",
            titulo="Ensure Content trust for Docker is Enabled",
            # Assinatura de imagem, não fixação por digest.
        ),
        RecomendacaoCIS(
            numero="4.6",
            titulo="Ensure that HEALTHCHECK instructions have been added to container images",
            controles=("CONF-DKR-002",),
        ),
        RecomendacaoCIS(
            numero="4.7",
            titulo="Ensure update instructions are not used alone in Dockerfiles",
            controles=("CONF-DKR-006",),
        ),
        RecomendacaoCIS(
            numero="4.8",
            titulo="Ensure setuid and setgid permissions are removed",
            # Bit setuid no sistema de arquivos da imagem. O CONF-DKR-008 é
            # permissão de escrita para todos, que é outra coisa.
        ),
        RecomendacaoCIS(
            numero="4.9",
            titulo="Ensure that COPY is used instead of ADD in Dockerfiles",
            controles=("CONF-DKR-003",),
        ),
        RecomendacaoCIS(
            numero="4.10",
            titulo="Ensure secrets are not stored in Dockerfiles",
            controles=("CONF-DKR-014", "CONF-SEC-001"),
        ),
        RecomendacaoCIS(
            numero="4.11",
            titulo="Ensure only verified packages are installed",
            # Instalar só o que foi verificado é a norma que condena executar
            # script remoto direto no shell, sem checksum.
            controles=("CONF-DKR-005",),
        ),
        RecomendacaoCIS(
            numero="4.12",
            titulo="Ensure all signed artifacts are validated",
        ),
        # ---------------------------- 5. Container Runtime Configuration
        RecomendacaoCIS(
            numero="5.1",
            titulo="Ensure swarm mode is not Enabled, if not needed",
        ),
        RecomendacaoCIS(
            numero="5.2",
            titulo="Ensure that, if applicable, an AppArmor Profile is enabled",
            # Não temos controle de AppArmor no catálogo.
        ),
        RecomendacaoCIS(
            numero="5.3",
            titulo="Ensure that, if applicable, SELinux security options are set",
        ),
        RecomendacaoCIS(
            numero="5.4",
            titulo="Ensure that Linux kernel capabilities are restricted within containers",
            controles=("CONF-WLD-005", "CONF-WLD-006"),
        ),
        RecomendacaoCIS(
            numero="5.5",
            titulo="Ensure that privileged containers are not used",
            controles=("CONF-WLD-001",),
        ),
        RecomendacaoCIS(
            numero="5.6",
            titulo="Ensure sensitive host system directories are not mounted on containers",
            controles=("CONF-WLD-003",),
        ),
        RecomendacaoCIS(
            numero="5.7",
            titulo="Ensure sshd is not run within containers",
            controles=("CONF-DKR-012",),
        ),
        RecomendacaoCIS(
            numero="5.8",
            titulo="Ensure privileged ports are not mapped within containers",
            # Porta abaixo de 1024. Nosso CONF-CMP-002 é sobre publicar em
            # todas as interfaces, que é a 5.14.
        ),
        RecomendacaoCIS(
            numero="5.9",
            titulo="Ensure that only needed ports are open on the container",
        ),
        RecomendacaoCIS(
            numero="5.10",
            titulo="Ensure that the host's network namespace is not shared",
            controles=("CONF-WLD-004",),
        ),
        RecomendacaoCIS(
            numero="5.11",
            titulo="Ensure that the memory usage for containers is limited",
            controles=("CONF-WLD-009",),
        ),
        RecomendacaoCIS(
            numero="5.12",
            titulo="Ensure that CPU priority is set appropriately on containers",
            controles=("CONF-WLD-009",),
        ),
        RecomendacaoCIS(
            numero="5.13",
            titulo="Ensure that the container's root filesystem is mounted as read only",
            controles=("CONF-WLD-008",),
        ),
        RecomendacaoCIS(
            numero="5.14",
            titulo=("Ensure that incoming container traffic is bound to a specific host interface"),
            controles=("CONF-CMP-002",),
        ),
        RecomendacaoCIS(
            numero="5.15",
            titulo="Ensure that the 'on-failure' container restart policy is set to '5'",
        ),
        RecomendacaoCIS(
            numero="5.16",
            titulo="Ensure that the host's process namespace is not shared",
            controles=("CONF-WLD-004",),
        ),
        RecomendacaoCIS(
            numero="5.17",
            titulo="Ensure that the host's IPC namespace is not shared",
            controles=("CONF-WLD-004",),
        ),
        RecomendacaoCIS(
            numero="5.18",
            titulo="Ensure that host devices are not directly exposed to containers",
            # Dispositivo do host via `--device`, não caminho de arquivo.
        ),
        RecomendacaoCIS(
            numero="5.19",
            titulo="Ensure that the default ulimit is overwritten at runtime if needed",
        ),
        RecomendacaoCIS(
            numero="5.20",
            titulo="Ensure mount propagation mode is not set to shared",
        ),
        RecomendacaoCIS(
            numero="5.21",
            titulo="Ensure that the host's UTS namespace is not shared",
            controles=("CONF-WLD-004",),
        ),
        RecomendacaoCIS(
            numero="5.22",
            titulo="Ensure the default seccomp profile is not Disabled",
            controles=("CONF-K8S-002",),
        ),
        RecomendacaoCIS(
            numero="5.23",
            titulo="Ensure that docker exec commands are not used with the privileged option",
            # `docker exec` é comando de operação: não aparece em Dockerfile,
            # compose nem manifesto, que é toda a entrada do sistema.
        ),
        RecomendacaoCIS(
            numero="5.24",
            titulo="Ensure that docker exec commands are not used with the user=root option",
        ),
        RecomendacaoCIS(
            numero="5.25",
            titulo="Ensure that cgroup usage is confirmed",
        ),
        RecomendacaoCIS(
            numero="5.26",
            titulo=("Ensure that the container is restricted from acquiring additional privileges"),
            # `no-new-privileges`, no Compose e no Kubernetes.
            controles=("CONF-CMP-001", "CONF-K8S-001"),
        ),
        RecomendacaoCIS(
            numero="5.27",
            titulo="Ensure that container health is checked at runtime",
            controles=("CONF-WLD-010",),
        ),
        RecomendacaoCIS(
            numero="5.28",
            titulo=(
                "Ensure that Docker commands always make use of the latest version of their image"
            ),
            # Condena depender de imagem obtida por tag móvel.
            controles=("CONF-IMG-001", "CONF-IMG-002"),
        ),
        RecomendacaoCIS(
            numero="5.29",
            titulo="Ensure that the PIDs cgroup limit is used",
        ),
        RecomendacaoCIS(
            numero="5.30",
            titulo='Ensure that Docker\'s default bridge "docker0" is not used',
        ),
        RecomendacaoCIS(
            numero="5.31",
            titulo="Ensure that the host's user namespaces are not shared",
            controles=("CONF-WLD-004",),
        ),
        RecomendacaoCIS(
            numero="5.32",
            titulo="Ensure that the Docker socket is not mounted inside any containers",
            controles=("CONF-WLD-002",),
        ),
    )
)
