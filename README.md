# Conformidade

Sistema multi-agente de conformidade para Docker e Kubernetes.

**Estado atual:** containerizado, com as camadas **1 (determinístico)** e
**2 (recuperação)** completas. Nada de Azure provisionado ainda — mas a
estrutura já está no formato que o Azure espera.

## Arquitetura alvo

```
arquivo do usuário
      ↓
[1] agente determinístico   parseia e roda regras fixas · sem LLM   ← implementado
      ↓  achados candidatos, cada um com control_id
[2] agente de recuperação   âncora canônica + busca híbrida        ← implementado
      ↓  documento do controle (PT) + trechos oficiais (EN)
[3] agente de análise       avalia contexto e combina
      ↓
[4] agente crítico          valida citação e coerência
      ↓
              relatório final
```

## Agente determinístico

Detecta o formato, parseia para um modelo normalizado e roda 36 controles.
Sem LLM, sem rede, sem relógio: a mesma entrada produz o mesmo relatório byte a
byte — propriedade coberta por teste, não só afirmada.

```bash
curl -X POST localhost:8000/api/v1/analyze -F "file=@Dockerfile"
curl localhost:8000/api/v1/controls        # catálogo que o corpus do RAG precisa cobrir
```

```python
from conformidade.agents.deterministic import analyze_path

report = analyze_path("Dockerfile")  # .artifact (parseado) + .findings (achados)
```

**Parsers escritos do zero**, sem embrulhar ferramenta existente:

| Formato | O que o parser trata |
|---|---|
| Dockerfile | diretivas `# syntax`/`# escape`, continuação com comentário no meio, heredoc, forma JSON vs. shell, flags (`--from`, `--mount`), multi-stage com referência entre stages |
| docker-compose | merge keys (`<<: *base`), as quatro formas de `ports`, bind vs. volume nomeado, `security_opt` com `:` ou `=` |
| Kubernetes | multi-documento, `securityContext` de pod sobreposto pelo do container, `volumeMounts` cruzado com `spec.volumes` para achar o tipo real, CronJob (dois níveis de aninhamento) |

**Catálogo de controles** — `control_id` próprio é a chave canônica; referências
a CIS/NIST são secundárias:

| Prefixo | Escopo | Qtd. |
|---|---|---|
| `CONF-WLD-*` | postura de runtime, vale para Compose e Kubernetes | 10 |
| `CONF-DKR-*` | específicos de Dockerfile | 15 |
| `CONF-K8S-*` | específicos de Kubernetes | 5 |
| `CONF-IMG-*` | procedência da imagem, vale para os três formatos | 3 |
| `CONF-CMP-*` | específicos de Compose | 2 |
| `CONF-SEC-*` | segredos | 1 |

Os 14 controles `CONF-WLD-*`/`CONF-IMG-*` são escritos uma vez e rodam em mais de
um formato — é o retorno de ter normalizado. Segredo detectado **nunca** sai em
claro: a estrutura parseada é redigida antes de virar relatório.

## Agente de recuperação — avaliação primeiro

A avaliação foi construída **antes** do retriever, de propósito: sem medição,
escolher entre lexical, híbrido ou grafo é opinião.

```bash
python scripts/medir_baseline.py --corpus <dir com as páginas>   # sai 1 se reprovar
```

| Artefato | O que é |
|---|---|
| [corpus/sources.yaml](corpus/sources.yaml) | 34 páginas, URLs e licenças verificadas. CIS fora (redistribuição restrita) |
| [corpus/cobertura.md](corpus/cobertura.md) | Medição de cobertura por controle e a linha de base |
| [evals/golden.yaml](evals/golden.yaml) | Gabarito: por controle, páginas de alta relevância, de apoio e **distratores** |
| [queries.py](src/conformidade/agents/retrieval/queries.py) | 36 consultas canônicas em inglês, escritas à mão (sem LLM em tempo de execução) |
| [controls/](src/conformidade/agents/retrieval/controls/) | 36 documentos canônicos em português — a âncora determinística |

O gabarito é declarado no nível de **página**, não de chunk — assim, mudar o
tamanho do chunk depois não invalida a medição.

**Resultado (busca híbrida, embedding local, custo zero):**

| modo | R@5 | R@10 | MRR | distratores |
|---|---|---|---|---|
| lexical (BM25) | 0.700 | **0.907** | 0.863 | 8 |
| denso (bge-small) | 0.748 | 0.897 | 0.862 | **4** |
| **híbrido (RRF)** | **0.752** | 0.901 | **0.877** | 5 |

Cada método erra diferente e a fusão aproveita os dois. O reranker cross-encoder
foi testado e **descartado por medição**: melhora P@5 mas piora MRR e não resolve
nenhum distrator.

Toda resposta traz também o **documento canônico** do controle — texto nosso, em
português, sempre presente. É o que garante a afirmação correta ao agente de
análise mesmo nos 5 controles em que a busca ainda traz um distrator.

**Linha de base anterior (BM25 puro, nível de página):**

```
recall@5   0.682  ✗      MRR       0.933
recall@10  0.814  ✗      nDCG@10   0.790  ✓
distratores no top-5: 6  ✗
```

MRR alto com recall médio diz que a busca lexical acerta *a primeira* página
relevante, mas perde as demais — que é justamente a lacuna que a busca densa
tende a fechar. E os 6 distratores confirmam os pares confundíveis
(`readOnlyRootFilesystem` × volume read-only, token de service account ×
Secret comum), provando que a avaliação discrimina de verdade.

## Portão de qualidade

```bash
make portao        # o mesmo comando que o CI executa
```

O workflow em [.github/workflows/ci.yml](.github/workflows/ci.yml) chama
exatamente este script — "passou local" e "passou no CI" significam a mesma
coisa. As actions estão fixadas por SHA de commit, e não por tag, pelo mesmo
motivo que o `CONF-IMG-003` exige digest em imagem: tag é ponteiro móvel.
O [Dependabot](.github/dependabot.yml) mantém os SHAs e a imagem base
atualizados — sem ele, fixar por digest vira congelar.

**O que bloqueia:**

| Verificação | Pega o quê |
|---|---|
| lint, formato, 245 testes | o de sempre |
| índice atualizado | alguém reingeriu o corpus e esqueceu de reindexar — o índice responderia com vetores de um conteúdo que não existe mais, sem erro nenhum |
| índice cobre todos os chunks | corpus e índice divergentes |
| sem regressão em 5 métricas | queda além de 0,01 contra a linha de base versionada |
| sem novos distratores | a distância até a meta aumentando em silêncio |

**O que informa mas não bloqueia:** as metas do gabarito. Hoje faltam 5
controles para o alvo de zero distratores. Se isso reprovasse, o portão ficaria
vermelho desde o primeiro dia — e portão permanentemente vermelho é portão que
a equipe aprende a ignorar. A distância aparece em toda execução, e a checagem
de regressão impede que ela cresça.

A linha de base fica em [evals/baseline_metricas.json](evals/baseline_metricas.json).
Depois de uma melhoria comprovada, `make baseline` a regrava — e um teste
reprova se ela ficar dessincronizada do estado real.

## Rodando local

```bash
docker compose up --build      # http://localhost:8000
curl localhost:8000/health/live
```

Sem Docker:

```bash
uv sync --extra dev
uv run conformidade-api
uv run pytest
```

## Estrutura

```
.
├── Dockerfile              # build multi-stage; produz a imagem que vai pro ACR
├── compose.yaml            # dev local espelhando as restrições do AKS
├── pyproject.toml          # dependências
├── uv.lock                 # build reprodutível (CI e Docker usam este lock)
├── docker/
│   └── entrypoint.sh       # roteia os roles (api | worker | shell)
├── src/conformidade/       # código da aplicação (src-layout)
│   ├── main.py             # API + health probes
│   ├── config.py           # settings via env vars
│   ├── logging.py          # log JSON no stdout
│   ├── api/                # rotas HTTP (finas: só traduzem para os agentes)
│   └── agents/
│       └── deterministic/  # camada 1 — sem LLM
│           ├── detector.py     # identifica o formato pelo conteúdo
│           ├── models.py       # modelo normalizado (pydantic)
│           ├── findings.py     # achado candidato + control_id
│           ├── sanitize.py     # redige segredo antes de sair
│           ├── parsers/        # dockerfile · compose · kubernetes
│           └── rules/          # 36 controles
├── tests/
├── infra/                  # Bicep — vazio, convenção do azd
├── deploy/k8s/             # manifestos AKS — vazio
└── .pipelines/             # Azure DevOps YAML — vazio
```

## Por que esta estrutura migra fácil para Azure

Cada escolha aqui existe para não ter que ser refeita depois:

| Escolha | O que destrava no Azure |
|---|---|
| `infra/` na raiz + estrutura azd | `azd init` / `azd up` funcionam sem reorganizar nada |
| Porta lida de `PORT` | Container Apps e App Service injetam a porta; não precisa rebuildar |
| `/health/live`, `/health/ready`, `/health/startup` separados | Mapeiam 1:1 nas probes do AKS e nos health probes do Container Apps |
| UID numérico 10001, não-root | Passa no Pod Security Standard `restricted` do AKS |
| Log JSON no stdout | Container Insights e Log Analytics fazem parse sem agente na imagem |
| Config 100% por env var | Vira env var do Deployment ou referência de secret do Key Vault |
| Imagem multi-role (`entrypoint.sh`) | Um repositório no ACR serve API e agentes; uma tag por commit |
| `uv.lock` versionado | Build determinístico no Azure Pipelines |
| Build multi-stage enxuto | Menos achados no Defender for Containers, push mais rápido |

Campos de Key Vault, App Configuration, Application Insights e managed identity
já existem em [config.py](src/conformidade/config.py), vazios — é só preencher
quando os recursos existirem.

## Próximas etapas

Agentes → Kubernetes/AKS → CI/CD no Azure DevOps → Bicep.
