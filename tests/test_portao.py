"""Testes do portão de qualidade.

Um portão que nunca reprova não protege nada. Estes testes provam que ele
reprova nos casos que motivaram sua existência — índice defasado e regressão
silenciosa —, e que não reprova por meta ainda não atingida.
"""

import json

import pytest

from conformidade.evals.harness import RelatorioEval
from conformidade.evals.portao import (
    TOLERANCIA,
    ResultadoPortao,
    executar,
    formatar,
    gravar_baseline,
    verificar_integridade,
    verificar_regressao,
)

RAIZ_CORPUS = "corpus"


def _relatorio(**kwargs) -> RelatorioEval:
    base = {
        "recall_at_5": 0.75,
        "recall_at_10": 0.90,
        "precision_at_5": 0.49,
        "mrr": 0.88,
        "ndcg_at_10": 0.78,
        "controles_com_distrator": 5,
    }
    return RelatorioEval(**{**base, **kwargs})


BASELINE = {
    "recall_at_5": 0.75,
    "recall_at_10": 0.90,
    "precision_at_5": 0.49,
    "mrr": 0.88,
    "ndcg_at_10": 0.78,
    "controles_com_distrator": 5,
}


# ------------------------------------------------- bloqueante × informativo


def test_meta_nao_atingida_nao_reprova():
    """A meta é o alvo, não o piso. Portão vermelho desde o dia um é portão
    que a equipe aprende a ignorar."""
    r = ResultadoPortao()
    r.adicionar("meta do gabarito", False, "5 distratores", bloqueante=False)
    assert r.aprovado
    assert len(r.metas_nao_atingidas) == 1


def test_falha_bloqueante_reprova():
    r = ResultadoPortao()
    r.adicionar("índice atualizado", False, "defasado")
    assert not r.aprovado


def test_relatorio_distingue_falha_de_meta():
    r = ResultadoPortao()
    r.adicionar("índice atualizado", True, "")
    r.adicionar("meta do gabarito", False, "5 distratores", bloqueante=False)
    texto = formatar(r)
    assert "[meta ]" in texto
    assert "[FALHA]" not in texto


# ------------------------------------------------------------- regressão


def test_regressao_detecta_queda_alem_da_tolerancia():
    quedas = verificar_regressao(_relatorio(recall_at_10=0.85), BASELINE)
    falhou = [v for v in quedas if not v.passou]
    assert [v.nome for v in falhou] == ["sem regressão em recall_at_10"]


def test_queda_dentro_da_tolerancia_passa():
    """Ruído de arredondamento não pode reprovar build."""
    dentro = BASELINE["recall_at_10"] - TOLERANCIA / 2
    quedas = verificar_regressao(_relatorio(recall_at_10=dentro), BASELINE)
    assert all(v.passou for v in quedas)


def test_melhora_nunca_reprova():
    quedas = verificar_regressao(_relatorio(recall_at_10=0.99, mrr=0.95), BASELINE)
    assert all(v.passou for v in quedas)


def test_novo_distrator_reprova():
    """É a defesa contra a distância até a meta aumentar em silêncio."""
    quedas = verificar_regressao(_relatorio(controles_com_distrator=6), BASELINE)
    falhou = [v for v in quedas if not v.passou]
    assert [v.nome for v in falhou] == ["sem novos distratores"]


def test_menos_distratores_passa():
    quedas = verificar_regressao(_relatorio(controles_com_distrator=3), BASELINE)
    assert all(v.passou for v in quedas)


def test_baseline_incompleta_ignora_metrica_ausente():
    quedas = verificar_regressao(_relatorio(), {"recall_at_10": 0.90})
    assert [v.nome for v in quedas] == ["sem regressão em recall_at_10"]


# ------------------------------------------------------------ integridade


def test_corpus_ausente_reprova(tmp_path):
    checagens = verificar_integridade(tmp_path / "nao-existe.jsonl", tmp_path)
    assert not checagens[0].passou


def test_indice_defasado_reprova(tmp_path, monkeypatch):
    """O caso real: reingerir o corpus e esquecer de reindexar. O índice
    continua respondendo, com vetores de um conteúdo que não existe mais."""
    import conformidade.evals.portao as portao

    monkeypatch.setattr(
        portao,
        "ler_meta",
        lambda _: {"modelo": "x", "corpus_versao": "versao-velha", "total_chunks": 1224},
    )
    checagens = verificar_integridade(
        portao.Path(RAIZ_CORPUS) / "chunks.jsonl", portao.Path(RAIZ_CORPUS) / "index"
    )
    defasado = [v for v in checagens if v.nome == "índice atualizado"]
    assert defasado and not defasado[0].passou
    assert "indexar.py" in defasado[0].detalhe


def test_contagem_divergente_reprova(tmp_path, monkeypatch):
    import conformidade.evals.portao as portao

    real = portao.ler_meta(portao.Path(RAIZ_CORPUS) / "index")
    monkeypatch.setattr(portao, "ler_meta", lambda _: {**real, "total_chunks": 999})
    checagens = verificar_integridade(
        portao.Path(RAIZ_CORPUS) / "chunks.jsonl", portao.Path(RAIZ_CORPUS) / "index"
    )
    cobertura = [v for v in checagens if v.nome == "índice cobre todos os chunks"]
    assert cobertura and not cobertura[0].passou


# --------------------------------------------------------- ponta a ponta


def test_portao_aprova_o_estado_atual():
    from pathlib import Path

    resultado = executar(
        Path(RAIZ_CORPUS) / "chunks.jsonl",
        Path(RAIZ_CORPUS) / "index",
        Path("evals") / "baseline_metricas.json",
    )
    assert resultado.aprovado, formatar(resultado)
    assert resultado.metricas["recall_at_10"] > 0.85


def test_baseline_ausente_reprova(tmp_path):
    from pathlib import Path

    resultado = executar(
        Path(RAIZ_CORPUS) / "chunks.jsonl",
        Path(RAIZ_CORPUS) / "index",
        tmp_path / "nao-existe.json",
    )
    assert not resultado.aprovado


def test_gravar_baseline_roundtrip(tmp_path):
    destino = tmp_path / "b.json"
    gravar_baseline(destino, {"recall_at_10": 0.9, "controles_com_distrator": 5})
    assert json.loads(destino.read_text())["recall_at_10"] == 0.9


def test_baseline_versionada_bate_com_o_estado_atual():
    """Se alguém melhorar a recuperação e esquecer de regravar a linha de base,
    o ganho não fica protegido contra regressão futura."""
    from pathlib import Path

    baseline = json.loads(Path("evals/baseline_metricas.json").read_text(encoding="utf-8"))
    resultado = executar(
        Path(RAIZ_CORPUS) / "chunks.jsonl",
        Path(RAIZ_CORPUS) / "index",
        Path("evals") / "baseline_metricas.json",
    )
    for metrica, valor in baseline.items():
        atual = resultado.metricas[metrica]
        assert atual == pytest.approx(valor, abs=TOLERANCIA), (
            f"{metrica}: atual {atual} × linha de base {valor} — "
            "rode `python scripts/portao.py --gravar-baseline`"
        )
