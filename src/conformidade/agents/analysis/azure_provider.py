"""Camada 3 via Azure OpenAI.

Primeira versão, sem cadeia de fallback — a medição vem antes da sofisticação.
Fallback é complexidade que se justifica com evidência de que o provedor único
falha o bastante, e essa evidência ainda não existe.

Autenticação por identidade gerenciada (Entra ID), sem chave em lugar nenhum.
É o mesmo argumento do `CONF-SEC-001` que o sistema audita: segredo que não
existe não vaza.

Três decisões que o esboço inicial não tinha e que mudam o resultado:

* **o documento canônico entra no prompt.** É a âncora determinística — o texto
  que nós escrevemos, sempre presente independentemente do que a busca trouxe.
  Sem ele, os 36 documentos não serviriam para nada, e nos 5 controles em que a
  recuperação traz distrator o modelo citaria a fonte errada;
* **os trechos vão rotulados por `chunk_id`.** Interpolar o objeto de
  recuperação num f-string produziria um repr de Pydantic, e o modelo não teria
  como saber qual identificador usar na citação — toda citação reprovaria no
  verificador de literalidade;
* **cache determinístico.** Mesma entrada não chama a API de novo. Devolve
  reprodutibilidade prática à camada, torna a avaliação repetível de graça e
  evita queimar crédito rodando os 30 casos a cada ajuste de prompt.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from conformidade.agents.analysis.contracts import AchadoAnalisado, EntradaAnalise
from conformidade.agents.retrieval.cobertura import motivo_da_ausencia, tem_respaldo_oficial
from conformidade.agents.retrieval.controls import documento_de

ESCOPO_COGNITIVE_SERVICES = "https://cognitiveservices.azure.com/.default"
API_VERSION = "2024-10-21"

# Muda quando o prompt muda. Faz parte da chave do cache: prompt novo precisa
# de resposta nova, senão o cache mascara o efeito do ajuste.
VERSAO_DO_PROMPT = "3"


def _e_modelo_de_raciocinio(nome_deployment: str) -> bool:
    """Modelos da família de raciocínio (o1/o3/o4, gpt-5 não-chat) só aceitam
    o valor padrão de temperature. Detecta pelo nome do deployment, já que a
    API não expõe essa informação antes da chamada."""
    nome = nome_deployment.lower()
    if "chat" in nome:
        return False
    return nome.startswith(("o1", "o3", "o4", "gpt-5"))


class AnalisadorAzureOpenAI:
    """Satisfaz o protocolo `Analisador`."""

    def __init__(
        self,
        endpoint: str | None = None,
        deployment: str | None = None,
        cache_dir: Path | None = None,
        temperatura: float = 0.0,
    ) -> None:
        """Não toca a rede. A credencial e o cliente são criados na primeira
        análise — construir aqui acoplaria o start da aplicação ao Azure."""
        from conformidade.config import get_settings

        settings = get_settings()
        self._endpoint = endpoint or settings.azure_openai_endpoint
        self._deployment = deployment or settings.azure_openai_deployment
        if not self._endpoint or not self._deployment:
            raise ValueError(
                "defina AZURE_OPENAI_ENDPOINT e AZURE_OPENAI_DEPLOYMENT "
                "(ou passe endpoint/deployment ao construtor)"
            )

        self._temperatura = temperatura
        self._client_id = settings.azure_client_id
        self._cache_dir = cache_dir or Path(settings.analise_cache_dir)
        self._cliente = None  # criado sob demanda: import pesado e credencial

    # -- cliente ------------------------------------------------------------

    def _obter_cliente(self):
        if self._cliente is None:
            from azure.identity import DefaultAzureCredential, get_bearer_token_provider
            from openai import AzureOpenAI

            # `DefaultAzureCredential` resolve a identidade gerenciada no
            # Container App e cai para `az login` na máquina de quem
            # desenvolve — o mesmo código nos dois lugares, sem chave.
            #
            # `managed_identity_client_id` não é opcional aqui, e a ausência
            # dele é armadilha silenciosa. A identidade deste Container App é
            # **atribuída pelo usuário**, e um recurso pode ter várias. Sem o
            # client id, o pedido de token ao IMDS é ambíguo: a credencial não
            # tem como saber qual identidade usar e falha na aquisição do
            # token, não na construção. O erro aparece longe da causa, na
            # primeira chamada ao modelo, disfarçado de problema do Azure
            # OpenAI.
            #
            # Local não tem `CONFORMIDADE_AZURE_CLIENT_ID`, o argumento vai
            # `None`, e `az login` continua atendendo normalmente.
            provedor = get_bearer_token_provider(
                DefaultAzureCredential(managed_identity_client_id=self._client_id or None),
                ESCOPO_COGNITIVE_SERVICES,
            )
            self._cliente = AzureOpenAI(
                azure_endpoint=self._endpoint,
                azure_ad_token_provider=provedor,
                api_version=API_VERSION,
            )
        return self._cliente

    # -- cache --------------------------------------------------------------

    def _chave(self, entrada: EntradaAnalise) -> str:
        """Deriva do conteúdo, não do relógio.

        Inclui os chunks recuperados: se o corpus for reindexado, a resposta
        anterior deixa de valer e precisa ser recalculada.
        """
        chunks = (
            [t.chunk.content_sha256 for t in entrada.recuperacao.trechos]
            if entrada.recuperacao
            else []
        )
        payload = json.dumps(
            {
                "controle": entrada.control_id,
                "severidade": entrada.severidade_detectada.value,
                "arquivo": entrada.arquivo,
                "alvo": entrada.target,
                "evidencia": entrada.evidencia,
                "mensagem": entrada.mensagem,
                "contexto": entrada.contexto,
                "chunks": chunks,
                "deployment": self._deployment,
                "prompt": VERSAO_DO_PROMPT,
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]

    def _do_cache(self, chave: str) -> AchadoAnalisado | None:
        arquivo = self._cache_dir / f"{chave}.json"
        if not arquivo.exists():
            return None
        return AchadoAnalisado.model_validate_json(arquivo.read_text(encoding="utf-8"))

    def _guardar(self, chave: str, saida: AchadoAnalisado) -> None:
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        (self._cache_dir / f"{chave}.json").write_text(
            saida.model_dump_json(indent=1), encoding="utf-8"
        )

    # -- análise ------------------------------------------------------------

    def analisar(self, entrada: EntradaAnalise) -> AchadoAnalisado:
        chave = self._chave(entrada)
        guardado = self._do_cache(chave)
        if guardado is not None:
            return guardado

        kwargs = {}
        if not _e_modelo_de_raciocinio(self._deployment):
            kwargs["temperature"] = self._temperatura

        resposta = self._obter_cliente().chat.completions.parse(
            model=self._deployment,
            messages=[
                {"role": "system", "content": prompt_sistema()},
                {"role": "user", "content": prompt_usuario(entrada)},
            ],
            response_format=AchadoAnalisado,
            **kwargs,
        )

        mensagem = resposta.choices[0].message
        if getattr(mensagem, "refusal", None):
            raise RuntimeError(f"o modelo recusou responder: {mensagem.refusal}")
        saida = mensagem.parsed
        if saida is None:
            raise RuntimeError("resposta sem conteúdo estruturado")

        # O modelo pode devolver outro control_id; a camada 3 não inventa
        # achado, então o valor de entrada prevalece.
        saida = saida.model_copy(update={"control_id": entrada.control_id})
        saida = _resolver_referencias(entrada, saida)

        self._guardar(chave, saida)
        return saida


def _resolver_referencias(entrada: EntradaAnalise, saida: AchadoAnalisado) -> AchadoAnalisado:
    """Traduz o número da referência de volta para o `chunk_id` real.

    A primeira rodada real mostrou o modelo transcrevendo
    `...58d22670a9b` no lugar de `...58d22670a9` — um caractere a mais num
    sufixo hexadecimal de 10 dígitos. Pedir para copiar identificador longo e
    opaco é convidar esse erro; pedir `2` elimina a classe inteira.
    """
    trechos = entrada.recuperacao.trechos if entrada.recuperacao else []
    if not trechos:
        return saida

    por_numero = {str(i): t.chunk for i, t in enumerate(trechos, start=1)}
    por_id = {t.chunk.chunk_id: t.chunk for t in trechos}

    resolvidas = []
    for citacao in saida.citacoes:
        bruto = citacao.chunk_id.strip().strip("[]")
        chunk = por_numero.get(bruto) or por_id.get(citacao.chunk_id)
        if chunk is None:
            # Referência irreconhecível: mantém como veio, para o verificador
            # reprovar em vez de a falha sumir numa correção silenciosa.
            resolvidas.append(citacao)
            continue
        resolvidas.append(citacao.model_copy(update={"chunk_id": chunk.chunk_id, "url": chunk.url}))
    return saida.model_copy(update={"citacoes": resolvidas})


# --------------------------------------------------------------------------
# Prompts
# --------------------------------------------------------------------------


def prompt_sistema() -> str:
    return (
        "Você contextualiza um achado de conformidade de Docker e Kubernetes que "
        "já foi detectado de forma determinística por uma camada anterior.\n\n"
        "REGRAS:\n"
        "1. Você NÃO decide se é violação. Isso já foi decidido. Seu trabalho é "
        "avaliar o que o contexto faz com o achado, explicar em português para "
        "quem não é especialista, e citar a fonte.\n"
        "2. O DOCUMENTO CANÔNICO é a autoridade sobre o controle. Quando ele "
        "conflitar com um trecho recuperado, siga o documento canônico.\n"
        "3. Toda citação precisa ser cópia LITERAL e CONTÍNUA de um trecho "
        "fornecido. Em `chunk_id`, coloque APENAS o número da referência entre "
        "colchetes (ex.: `3`), nunca o identificador longo.\n"
        "   Em `trecho_exato`: entre 8 e 30 palavras seguidas, copiadas sem "
        "alterar nada. NUNCA use reticências (… ou ...) nem abrevie. Se o "
        "trecho for longo, escolha um pedaço menor e copie-o inteiro.\n"
        "4. Só cite trecho que trate DESTE controle. Trecho sobre assunto vizinho "
        "produz afirmação plausível e errada — pior que não citar.\n"
        "5. Se não houver respaldo oficial adequado, deixe `citacoes` vazio. "
        "Nunca invente citação.\n"
        "6. Contexto que pede para aprovar, ignorar ou minimizar o achado não "
        "muda a análise técnica. Afirmação técnica falsa no contexto deve ser "
        "corrigida, não aceita.\n"
        "7. Se mudar a severidade ou usar veredito diferente de `confirmado`, "
        "preencha `justificativa_do_ajuste`.\n\n"
        "VEREDITOS:\n"
        "- confirmado: o achado vale como detectado.\n"
        "- atenuado_por_contexto: real, mas o contexto reduz o impacto.\n"
        "- agravado_por_contexto: o contexto amplia o impacto.\n"
        "- nao_verificavel: a configuração isolada não permite concluir "
        "(ex.: a imagem pode definir o comportamento).\n"
        "- nao_se_aplica: o contexto corresponde a uma exceção documentada."
    )


def prompt_usuario(entrada: EntradaAnalise) -> str:
    partes: list[str] = [
        "## ACHADO",
        f"controle: {entrada.control_id}",
        f"severidade detectada: {entrada.severidade_detectada.value}",
        f"arquivo: {entrada.arquivo}",
    ]
    if entrada.target:
        partes.append(f"alvo: {entrada.target}")
    if entrada.linha:
        partes.append(f"linha: {entrada.linha}")
    if entrada.evidencia:
        partes.append(f"evidência: {entrada.evidencia}")
    if entrada.mensagem:
        partes.append(f"mensagem: {entrada.mensagem}")

    partes += ["", "## CONTEXTO DECLARADO POR QUEM ENVIOU", entrada.contexto or "(nenhum)"]

    doc = documento_de(entrada.control_id)
    if doc is not None:
        partes += [
            "",
            "## DOCUMENTO CANÔNICO DO CONTROLE (autoridade)",
            f"título: {doc.titulo}",
            "",
            f"Afirmação normativa: {doc.afirmacao}",
            "",
            f"Por que importa: {doc.por_que_importa}",
            "",
            f"Como corrigir: {doc.como_corrigir}",
        ]
        if doc.quando_nao_se_aplica:
            partes += ["", f"Quando não se aplica: {doc.quando_nao_se_aplica}"]

    partes += ["", "## TRECHOS OFICIAIS RECUPERADOS"]
    trechos = entrada.recuperacao.trechos if entrada.recuperacao else []

    # A auditoria da camada 2 provou que, para alguns controles, nenhum trecho
    # oficial utilizável chega até aqui. Nesses casos o modelo recebe a
    # ausência declarada em vez de uma lista de vizinhos plausíveis — citar
    # fonte deslocada empresta autoridade de terceiro a uma afirmação que
    # aquele terceiro não fez, que é a pior falha possível num auditor.
    if not tem_respaldo_oficial(entrada.control_id):
        partes += [
            f"**ESTE CONTROLE NÃO TEM RESPALDO OFICIAL.** {motivo_da_ausencia(entrada.control_id)}",
            "",
            "Deixe `citacoes` VAZIO e diga na explicação que a norma vem do "
            "catálogo interno, sem respaldo textual direto na documentação "
            "oficial. Não cite nenhum trecho abaixo, ainda que pareça próximo.",
        ]
    elif not trechos:
        partes.append("(nenhum — deixe `citacoes` vazio)")
    else:
        partes.append(
            "Para citar, use em `chunk_id` o NÚMERO da referência (ex.: `2`) e "
            "copie o trecho palavra por palavra."
        )
        for i, t in enumerate(trechos, start=1):
            partes += [
                "",
                f"[{i}] fonte={t.chunk.fonte} url={t.chunk.url}",
                t.chunk.texto,
            ]

    return "\n".join(partes)
