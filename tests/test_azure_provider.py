"""Testes do provedor Azure OpenAI.

Nenhum toca a rede. O que dá para verificar offline é justamente o que quebra
em produção de forma cara: schema incompatível com Structured Outputs, prompt
sem a informação necessária para citar, e cache que não invalida quando devia.
"""

import json

import pytest

from conformidade.agents.analysis.azure_provider import (
    VERSAO_DO_PROMPT,
    AnalisadorAzureOpenAI,
    prompt_sistema,
    prompt_usuario,
)
from conformidade.agents.analysis.contracts import (
    AchadoAnalisado,
    Citacao,
    Confianca,
    EntradaAnalise,
    Veredito,
)
from conformidade.agents.deterministic.models import Severity
from conformidade.agents.retrieval.contracts import Chunk, ResultadoRecuperacao, TrechoRecuperado


def _chunk(chunk_id: str, texto: str, page_id: str = "dkr:x") -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        page_id=page_id,
        url="https://exemplo/x",
        fonte="docker",
        licenca="Apache-2.0",
        camada=1,
        doc_versao="v",
        heading_path="H",
        texto=texto,
        content_sha256=chunk_id,
    )


def _entrada(**kwargs) -> EntradaAnalise:
    base = {
        "arquivo": "compose.yaml",
        "control_id": "CONF-WLD-002",
        "severidade_detectada": Severity.CRITICAL,
        "target": "api",
        "linha": 10,
        "evidencia": "/var/run/docker.sock",
        "mensagem": "Monta o socket do runtime.",
        "contexto": "Worker de fila que não constrói imagem.",
        "recuperacao": ResultadoRecuperacao(
            control_id="CONF-WLD-002",
            consulta="q",
            trechos=[
                TrechoRecuperado(
                    chunk=_chunk("dkr:a#0001-aa", "mounting the docker socket is dangerous"),
                    score=1.0,
                    posicao=0,
                )
            ],
        ),
    }
    return EntradaAnalise(**{**base, **kwargs})


# ------------------------------------------- compatibilidade com o Azure


def test_schema_e_compativel_com_structured_outputs():
    """O Azure exige schema strict: todo campo obrigatório e sem propriedade
    extra. Um campo com default que escape disso vira 400 em runtime."""
    from openai.lib._pydantic import to_strict_json_schema

    schema = to_strict_json_schema(AchadoAnalisado)
    assert schema["additionalProperties"] is False
    assert set(schema["properties"]) == set(schema["required"])


def test_citacao_tambem_e_strict():
    from openai.lib._pydantic import to_strict_json_schema

    schema = to_strict_json_schema(AchadoAnalisado)
    citacao = schema["$defs"]["Citacao"]
    assert citacao["additionalProperties"] is False
    assert set(citacao["properties"]) == set(citacao["required"])


# --------------------------------------------------------------- prompt


def test_prompt_inclui_o_documento_canonico():
    """A âncora é a autoridade sobre o controle. Sem ela no prompt, os 36
    documentos não serviriam para nada e o modelo seguiria o trecho recuperado
    mesmo quando ele for o distrator."""
    u = prompt_usuario(_entrada())
    assert "DOCUMENTO CANÔNICO" in u
    assert "socket" in u.lower()


def test_prompt_numera_as_referencias():
    """A primeira rodada real mostrou o modelo transcrevendo `...58d22670a9b`
    no lugar de `...58d22670a9`. Pedir para copiar hash de 10 dígitos convida
    o erro; pedir `1` elimina a classe."""
    u = prompt_usuario(_entrada())
    assert "[1] fonte=" in u
    assert "dkr:a#0001-aa" not in u


def test_referencia_numerica_vira_chunk_id_real():
    from conformidade.agents.analysis.azure_provider import _resolver_referencias

    entrada = _entrada()
    saida = AchadoAnalisado(
        control_id="CONF-WLD-002",
        veredito=Veredito.CONFIRMADO,
        severidade_ajustada=Severity.CRITICAL,
        explicacao="Explicação longa o suficiente para o verificador considerar substancial.",
        como_corrigir="Remova a montagem do socket.",
        citacoes=[Citacao(chunk_id="1", trecho_exato="mounting the docker socket is dangerous")],
        confianca=Confianca.ALTA,
    )
    resolvida = _resolver_referencias(entrada, saida)
    assert resolvida.citacoes[0].chunk_id == "dkr:a#0001-aa"


def test_referencia_irreconhecivel_nao_e_corrigida_em_silencio():
    """Se o modelo inventar uma referência, o verificador precisa reprovar —
    não pode sumir numa correção silenciosa."""
    from conformidade.agents.analysis.azure_provider import _resolver_referencias

    saida = AchadoAnalisado(
        control_id="CONF-WLD-002",
        veredito=Veredito.CONFIRMADO,
        severidade_ajustada=Severity.CRITICAL,
        explicacao="Explicação longa o suficiente para o verificador considerar substancial.",
        como_corrigir="Remova a montagem do socket.",
        citacoes=[Citacao(chunk_id="99", trecho_exato="texto qualquer inventado aqui")],
        confianca=Confianca.ALTA,
    )
    assert _resolver_referencias(_entrada(), saida).citacoes[0].chunk_id == "99"


def test_prompt_inclui_o_texto_integral_do_trecho():
    """Citação precisa ser literal; o modelo só consegue copiar o que viu."""
    u = prompt_usuario(_entrada())
    assert "mounting the docker socket is dangerous" in u


def test_prompt_sem_recuperacao_orienta_a_nao_citar():
    entrada = _entrada(recuperacao=ResultadoRecuperacao(control_id="X", consulta="", trechos=[]))
    assert "deixe `citacoes` vazio" in prompt_usuario(entrada)


def test_sistema_proibe_inventar_citacao():
    s = prompt_sistema()
    assert "Nunca invente citação" in s
    assert "NÃO decide se é violação" in s


def test_sistema_orienta_a_resistir_a_pressao():
    """Nível 6 da avaliação: contexto pedindo aprovação não muda a análise."""
    assert "não muda a análise técnica" in prompt_sistema()


# ---------------------------------------------------------------- cache


def _provedor(tmp_path) -> AnalisadorAzureOpenAI:
    return AnalisadorAzureOpenAI(
        endpoint="https://exemplo.openai.azure.com/",
        deployment="gpt-4o-mini",
        cache_dir=tmp_path,
    )


def test_chave_do_cache_e_estavel(tmp_path):
    p = _provedor(tmp_path)
    assert p._chave(_entrada()) == p._chave(_entrada())


def test_chave_muda_com_o_contexto(tmp_path):
    p = _provedor(tmp_path)
    assert p._chave(_entrada()) != p._chave(_entrada(contexto="outro contexto qualquer"))


def test_chave_muda_quando_o_corpus_e_reindexado(tmp_path):
    """Se os chunks mudam, a resposta anterior deixa de valer."""
    p = _provedor(tmp_path)
    outra = ResultadoRecuperacao(
        control_id="CONF-WLD-002",
        consulta="q",
        trechos=[
            TrechoRecuperado(chunk=_chunk("dkr:b#0002-bb", "outro texto"), score=1.0, posicao=0)
        ],
    )
    assert p._chave(_entrada()) != p._chave(_entrada(recuperacao=outra))


def test_cache_faz_roundtrip(tmp_path):
    p = _provedor(tmp_path)
    saida = AchadoAnalisado(
        control_id="CONF-WLD-002",
        veredito=Veredito.CONFIRMADO,
        severidade_ajustada=Severity.CRITICAL,
        explicacao="Montar o socket dá acesso equivalente a root no host da máquina.",
        como_corrigir="Remova a montagem do socket do compose.",
        citacoes=[Citacao(chunk_id="dkr:a#0001-aa", trecho_exato="the docker socket is dangerous")],
        confianca=Confianca.ALTA,
    )
    chave = p._chave(_entrada())
    p._guardar(chave, saida)
    assert p._do_cache(chave) == saida


def test_cache_vazio_devolve_none(tmp_path):
    assert _provedor(tmp_path)._do_cache("nao-existe") is None


def test_versao_do_prompt_entra_na_chave(tmp_path):
    """Prompt novo precisa de resposta nova — senão o cache mascara o efeito
    do ajuste que se está tentando medir."""
    p = _provedor(tmp_path)
    import conformidade.agents.analysis.azure_provider as mod

    antes = p._chave(_entrada())
    original = mod.VERSAO_DO_PROMPT
    try:
        mod.VERSAO_DO_PROMPT = "999"
        depois = p._chave(_entrada())
    finally:
        mod.VERSAO_DO_PROMPT = original
    assert antes != depois
    assert VERSAO_DO_PROMPT == original


# ------------------------------------------------------------- validação


def test_falta_de_configuracao_falha_explicitamente(monkeypatch):
    """Melhor erro claro na construção do que 401 obscuro na primeira chamada."""
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_DEPLOYMENT", raising=False)
    from conformidade.config import get_settings

    get_settings.cache_clear()
    with pytest.raises(ValueError, match="AZURE_OPENAI_ENDPOINT"):
        AnalisadorAzureOpenAI()
    get_settings.cache_clear()


def test_saida_serializa_para_json_valido():
    saida = AchadoAnalisado(
        control_id="CONF-WLD-002",
        veredito=Veredito.NAO_SE_APLICA,
        severidade_ajustada=Severity.LOW,
        justificativa_do_ajuste="O contexto corresponde à exceção documentada.",
        explicacao="Explicação suficientemente longa para o verificador aceitar como substancial.",
        como_corrigir="Nenhuma ação necessária neste contexto específico.",
        confianca=Confianca.MEDIA,
    )
    assert json.loads(saida.model_dump_json())["veredito"] == "nao_se_aplica"
