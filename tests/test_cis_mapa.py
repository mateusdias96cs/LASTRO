"""Correspondência entre o mapa do CIS e o documento real.

O risco que estes testes existem para eliminar: o mapa apontar para
recomendação que não existe, ou o documento trazer recomendação que ninguém
declarou. Nos dois casos a falha é silenciosa — nada quebra, o gabarito
simplesmente passa a descrever um documento imaginário.

Os testes que exigem o PDF pulam quando ele não está no cache local, porque a
licença CC BY-NC-SA mantém o arquivo fora do repositório.
"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from conformidade.agents.retrieval.cis import MAPA, PAGE_ID, MapaCIS, RecomendacaoCIS
from conformidade.agents.retrieval.controls import DIRETORIO
from conformidade.agents.retrieval.ingest.extract import extrair_cis

PDF = Path(__file__).resolve().parents[1] / ".corpus-cache" / "CIS_Docker_Benchmark_v1.8.0.pdf"
precisa_do_pdf = pytest.mark.skipif(not PDF.exists(), reason="CIS PDF não está no cache local")


def _do_pdf() -> dict[str, str]:
    """numero -> titulo, como o extrator realmente lê."""
    saida = {}
    for s in extrair_cis(str(PDF)):
        ultimo = s.heading_path.rsplit(" > ", 1)[-1]
        numero, titulo = ultimo.split(" ", 1)
        saida[numero] = titulo
    return saida


# ------------------------------------------------- validação do próprio mapa


def test_mapa_carrega():
    assert len(MAPA.recomendacoes) == 44


def test_numero_fora_do_escopo_e_rejeitado():
    """Seção 1 é host, 7 é Swarm — nada disso entra no corpus."""
    with pytest.raises(ValidationError, match="fora das seções 4 e 5"):
        RecomendacaoCIS(numero="1.1", titulo="Ensure something about the host")


def test_control_id_inexistente_e_rejeitado():
    """Sem isto, um typo viraria mapeamento que não mapeia nada."""
    with pytest.raises(ValidationError, match="inexistente no catálogo"):
        RecomendacaoCIS(
            numero="5.13",
            titulo="Ensure that the container's root filesystem is mounted as read only",
            controles=("CONF-WLD-999",),
        )


def test_control_id_repetido_e_rejeitado():
    with pytest.raises(ValidationError, match="repetido"):
        RecomendacaoCIS(
            numero="5.5",
            titulo="Ensure that privileged containers are not used",
            controles=("CONF-WLD-001", "CONF-WLD-001"),
        )


def test_titulo_nao_normalizado_e_rejeitado():
    with pytest.raises(ValidationError, match="não normalizado"):
        RecomendacaoCIS(numero="5.5", titulo="  Ensure that privileged containers  ")


def test_recomendacao_duplicada_e_rejeitada():
    with pytest.raises(ValidationError, match="declarada duas vezes"):
        MapaCIS(
            recomendacoes=(
                RecomendacaoCIS(numero="5.5", titulo="Ensure that privileged containers"),
                RecomendacaoCIS(numero="5.5", titulo="Ensure that privileged containers"),
            )
        )


def test_todo_controle_mapeado_existe():
    catalogo = {p.stem for p in DIRETORIO.glob("*.md")}
    assert MAPA.controles_cobertos() <= catalogo


def test_mapa_e_conservador():
    """Metade das recomendações não mapeia nada, e isso é o esperado: o CIS
    cobre host, Swarm e operação além do que auditamos. Se este número subir
    para perto de 44, é sinal de que alguém mapeou por resultado."""
    com_controle = [r for r in MAPA.recomendacoes if r.controles]
    assert 15 <= len(com_controle) <= 30


# --------------------------------------------- correspondência com o PDF


@precisa_do_pdf
def test_todo_numero_do_mapa_existe_no_pdf():
    faltando = sorted(MAPA.numeros() - set(_do_pdf()))
    assert not faltando, f"mapa aponta para recomendação inexistente: {faltando}"


@precisa_do_pdf
def test_toda_recomendacao_do_pdf_esta_no_mapa():
    """Recomendação nova numa versão futura do CIS não pode passar
    despercebida: ela precisa ser lida e mapeada, ou explicitamente deixada
    sem controle."""
    faltando = sorted(set(_do_pdf()) - MAPA.numeros())
    assert not faltando, f"recomendação do PDF não declarada no mapa: {faltando}"


@precisa_do_pdf
def test_titulos_batem_literalmente():
    """Renumeração ou reescrita entre versões do CIS tem de falhar aqui, não
    virar mapeamento silenciosamente errado."""
    do_pdf = _do_pdf()
    divergentes = [
        (r.numero, r.titulo, do_pdf[r.numero])
        for r in MAPA.recomendacoes
        if do_pdf.get(r.numero) != r.titulo
    ]
    assert not divergentes, f"título divergente entre mapa e PDF: {divergentes}"


GANHARAM_RESPALDO = {"CONF-DKR-006", "CONF-WLD-005"}


def test_o_cis_mapeia_quem_ganhou_respaldo():
    """Registra o motivo de o CIS entrar no corpus.

    Antes da ativação, estes dois declaravam falta de respaldo oficial. Com o
    CIS indexado, a auditoria passou a entregar trecho normativo para os dois —
    `CONF-DKR-006` pela recomendação 4.7 na primeira posição, `CONF-WLD-005`
    pela 5.4 na sexta. Se o mapeamento sumir, a causa do ganho sumiu junto.
    """
    assert GANHARAM_RESPALDO <= MAPA.controles_cobertos()


def test_quem_ganhou_respaldo_saiu_da_lista_de_ausencia():
    """Impede a regressão silenciosa oposta: o controle voltar a declarar
    ausência de respaldo enquanto a fonte continua no corpus."""
    from conformidade.agents.retrieval.cobertura import SEM_RESPALDO_OFICIAL

    assert not (GANHARAM_RESPALDO & set(SEM_RESPALDO_OFICIAL))


def test_quem_ainda_declara_ausencia_nao_e_promessa_vazia():
    """Controle que segue sem respaldo e ESTÁ mapeado no CIS é sinal de que a
    fonte existe e a busca não a entrega — situação real de `CONF-WLD-008` e
    `CONF-WLD-009`, e que a auditoria detalha. O que não pode existir é
    controle sem respaldo cuja causa ninguém saiba nomear."""
    from conformidade.agents.retrieval.cobertura import SEM_RESPALDO_OFICIAL

    for control_id, motivo in SEM_RESPALDO_OFICIAL.items():
        assert motivo.strip(), control_id


# --------------------------------------------- correspondência com o gabarito


cis_ativo = pytest.mark.skipif(
    PAGE_ID
    not in (Path(__file__).resolve().parents[1] / "corpus" / "sources.yaml").read_text(
        encoding="utf-8"
    ),
    reason="CIS ainda não ativado no manifesto do corpus",
)


@cis_ativo
def test_gabarito_declara_o_cis_para_todo_controle_mapeado():
    """Mapa e gabarito não podem divergir. Mapear um controle e esquecer de
    declarar a fonte no gabarito faria a métrica contar o CIS como erro; o
    inverso faria o gabarito prometer fonte que ninguém mapeou."""
    from conformidade.evals.golden import carregar_gabarito

    gabarito = carregar_gabarito()
    for control_id in sorted(MAPA.controles_cobertos()):
        caso = gabarito.caso(control_id)
        assert caso is not None, control_id
        assert PAGE_ID in caso.alta, f"{control_id} mapeado mas sem {PAGE_ID} em `alta`"


@cis_ativo
def test_gabarito_nao_declara_cis_onde_nao_ha_mapeamento():
    from conformidade.evals.golden import carregar_gabarito

    cobertos = MAPA.controles_cobertos()
    for control_id, caso in carregar_gabarito().casos.items():
        if control_id in cobertos:
            continue
        assert PAGE_ID not in caso.relevantes, (
            f"{control_id} promete {PAGE_ID} sem recomendação mapeada"
        )
