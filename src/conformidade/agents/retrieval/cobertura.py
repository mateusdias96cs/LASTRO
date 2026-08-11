"""Quais controles têm respaldo textual oficial — e quais não têm.

Este módulo existe por uma decisão de honestidade que o projeto tomou tarde:
**quando não há fonte oficial, o relatório diz que não há**, em vez de citar o
trecho mais parecido que a busca encontrou.

A razão é específica de uma ferramenta de auditoria. Citação plausível e
deslocada é pior que nenhuma citação: ela transfere autoridade de terceiro para
uma afirmação que aquele terceiro não fez. A auditoria da camada 2 mediu isso —
em quatro controles o distrator aparecia **acima** da fonte verdadeira, e no
`CONF-SEC-001` ele era o primeiro resultado.

A lista abaixo não é opinião. Sai de `scripts/auditar_camada2.py`, que verifica,
para cada controle, se algum chunk portador de um identificador normativo
discriminativo chega ao top-6 entregue à camada 3. Os identificadores vêm da
seção `Afirmação normativa` dos documentos canônicos, escritos antes da
auditoria existir; o corte de relevância é derivado da chance de acerto ao acaso
num top-6 aleatório, não escolhido.

Importante: **isto não afirma que a documentação oficial não trata do assunto.**
Afirma que o sistema, como está, não entrega um trecho oficial utilizável para
este controle. As duas causas medidas são distintas:

* `apagado_pelo_agrupamento` — a busca acha o trecho, e a política de um chunk
  por página o remove do resultado. Medido: afrouxar a política piora o
  conjunto (ver `index/hybrid.py`);
* `fora_do_k_entregue` — o trecho existe abaixo da sexta posição. Medido: subir
  o `k` ganha um controle e quase triplica a exposição a distratores.

Quando um desses controles passar a receber trecho normativo, a auditoria
acusa e a entrada sai daqui. O teste em `tests/test_cobertura.py` impede que a
lista e a medição divirjam em silêncio.
"""

from __future__ import annotations

# control_id → por que não há respaldo entregue, em linguagem de relatório.
SEM_RESPALDO_OFICIAL: dict[str, str] = {
    "CONF-DKR-006": (
        "A documentação oficial da Docker menciona `apt-get upgrade` apenas em "
        "texto sobre invalidação de cache de build, não como recomendação de "
        "segurança."
    ),
    "CONF-DKR-011": (
        "Não há, na documentação oficial indexada, enunciado normativo sobre "
        "restringir o contexto de build enviado à imagem."
    ),
    "CONF-IMG-002": (
        "A documentação oficial descreve o comportamento de tags mutáveis, mas "
        "não enuncia norma sobre quais tags evitar."
    ),
    "CONF-WLD-005": (
        "A documentação oficial lista as capabilities do Linux e o que cada uma "
        "faz, sem enunciar quais devem ser negadas."
    ),
    "CONF-WLD-008": (
        "`readOnlyRootFilesystem` aparece na documentação oficial apenas em "
        "página de tutorial de configuração, sem enunciado normativo."
    ),
    "CONF-WLD-009": (
        "A documentação oficial explica como limites de recurso funcionam, sem "
        "enunciar que declará-los é obrigatório."
    ),
}

AVISO_PADRAO = (
    "Sem respaldo textual direto na documentação oficial indexada. "
    "A norma abaixo é do catálogo interno deste sistema."
)


def tem_respaldo_oficial(control_id: str) -> bool:
    """`False` quando a auditoria provou que nenhum trecho oficial utilizável
    chega à camada de análise para este controle."""
    return control_id not in SEM_RESPALDO_OFICIAL


def motivo_da_ausencia(control_id: str) -> str:
    """Texto para o relatório. Vazio quando há respaldo."""
    return SEM_RESPALDO_OFICIAL.get(control_id, "")
