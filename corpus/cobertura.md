# Cobertura do corpus e linha de base — Fases 0 e 1

Relatório da medição que fundamenta `corpus/sources.yaml` e `evals/golden.yaml`.
Nada aqui é estimativa: são contagens sobre as páginas realmente baixadas.

## Fase 0 — Fontes

34 URLs verificadas (HTTP 200). Licenças conferidas no `LICENSE` de cada
repositório de origem:

| Fonte | Licença | Verificado em |
|---|---|---|
| docker/docs | **Apache-2.0** | `LICENSE` do repositório |
| kubernetes/website | **CC BY 4.0** (Attribution 4.0 International) | `LICENSE` do repositório |
| NIST SP 800-190 | Domínio público (obra do governo dos EUA) | PDF público, 666 KB |

Excluídas por decisão registrada em `sources.yaml`: CIS Benchmarks
(redistribuição restrita — só o número da cláusula é usado), man-pages do Linux
(licenciamento heterogêneo) e OWASP Cheat Sheets (CC BY-SA, adiado).

## Cobertura por controle

Método: extração de texto das 34 páginas e contagem de frases-sonda específicas
por controle. A primeira rodada usou palavras soltas (`tag`, `root`, `secret`) e
produziu 5 falsos "sem cobertura" — as sondas foram refeitas com frases
específicas (`:latest`, `runAsNonRoot`, `secretKeyRef`).

Resultado: **0 controles sem cobertura**. 7 controles com menos de 3 páginas:

| Controle | Páginas | Observação |
|---|---|---|
| `CONF-DKR-009` | 1 | Limpeza de cache do apt |
| `CONF-K8S-005` | 1 | hostPort |
| `CONF-DKR-004` | 2 | ADD remoto |
| `CONF-DKR-006` | 2 | apt-get upgrade |
| `CONF-DKR-010` | 2 | `--no-install-recommends` |
| `CONF-CMP-001` | 2 | no-new-privileges |
| `CONF-WLD-004` | 2 | **Controle grave com cobertura fina** |

`CONF-WLD-004` (namespaces do host) é o que mais preocupa: risco alto e apenas
duas páginas. Candidato número um a ampliação de corpus.

## Fase 1 — Linha de base

BM25 escrito do zero, no nível de página, sem embedding e sem banco.
33 das 34 páginas (o PDF do NIST ainda não foi ingerido — a Fase 2 trata PDF).

```
controles avaliados : 36
recall@5            : 0.682   (mínimo 0.75)  ✗
recall@10           : 0.814   (mínimo 0.90)  ✗
precision@5         : 0.422
MRR                 : 0.933
nDCG@10             : 0.790   (mínimo 0.65)  ✓
com distrator top-5 : 6       (máximo 0)     ✗
```

### Como ler esse resultado

**MRR de 0,933 com recall@10 de 0,814** é o achado mais informativo. Os dois
juntos dizem que a busca lexical quase sempre acerta *a primeira* página
relevante, mas perde as *demais*. Ou seja: o problema não é "encontrar algo
pertinente" — é reunir todo o respaldo. É exatamente o tipo de lacuna que a
busca densa tende a fechar, porque ela acha a página que usa outra redação para
o mesmo conceito.

**Os 6 distratores confirmam a hipótese dos pares confundíveis**, e nos casos
previstos no gabarito:

| Controle | Distrator que subiu | Por quê |
|---|---|---|
| `CONF-WLD-008` | `dkr:bind-mounts`, `k8s:volumes` | "raiz somente-leitura" × "volume montado somente-leitura" |
| `CONF-K8S-003` | `k8s:secrets` | token de service account × Secret comum |
| `CONF-CMP-002` | `k8s:service` | publicação de porta × Service |
| `CONF-DKR-007` | `k8s:rbac` | "privilégio" em dois sentidos |
| `CONF-WLD-009` | `k8s:rbac` | "limites" e "quota" |
| `CONF-WLD-001` | `dkr:compose-build` | casamento incidental |

Isso valida o desenho da avaliação: os casos adversariais têm poder de
discriminação real, não são enfeite.

## Revisão 2 — gabarito conferido contra o conteúdo

A versão 1 do gabarito veio de contagem de termos e julgamento. A revisão
conferiu cada página marcada `alta` contra o texto real. **Seis entradas não
sobreviveram** (detalhe no cabeçalho de `evals/golden.yaml`), entre elas:

- `CONF-DKR-006` apontava para uma página com **zero** ocorrência de
  "apt-get upgrade";
- `CONF-K8S-005` apontava para uma página que **nunca menciona** `hostPort`;
- `CONF-SEC-001` tinha como fonte normativa a página de segredo de **build**
  (14 menções a build contra 2 de runtime) — contradizendo a nota do próprio
  caso, que dizia serem controles distintos.

O PDF do NIST foi extraído (63 páginas, 163k caracteres) e entrou no corpus.

### Números da revisão 2

```
recall@5    0.678   (era 0.682)
recall@10   0.816   (era 0.814)
MRR         0.933   (igual)
nDCG@10     0.782   (era 0.790)
distratores 5       (eram 6)
```

### Uma previsão minha que estava errada

Na revisão 1 escrevi que o recall reportado era "piso conservador" e que
incluir o NIST o elevaria. **Não elevou**: 0,814 → 0,816, praticamente nada.

A causa está medida:

| Documento | Tokens |
|---|---|
| `nist:sp-800-190` | **22.560** |
| média do corpus | 7.462 |

A normalização por tamanho do BM25 penaliza documentos longos. Com 3× a média,
o NIST quase nunca sobe ao top-10 — e **não aparece nem no `CONF-DKR-006`**,
onde agora é a fonte principal, apesar de conter 89 ocorrências de
patch/vulnerabilidade.

Isso vira um requisito duro para a Fase 2: um documento de 63 páginas tratado
como unidade única de recuperação é **invisível na prática**. O chunking não é
refinamento, é o que torna o NIST utilizável — e a previsão é que ele sozinho,
antes de qualquer embedding, já melhore o recall.

## Fase 2 — Ingestão e chunking

34 páginas → 1.045 seções → **1.224 chunks**, nenhum acima de 480 tokens.
Reingerir do cache produz um `chunks.jsonl` byte a byte idêntico.

### A previsão se confirmou

| Métrica | Página | Chunk | Δ |
|---|---|---|---|
| **recall@10** | 0.816 | **0.907** | **+0.091** ✓ passou o limiar |
| recall@5 | 0.678 | 0.700 | +0.022 |
| precision@5 | 0.422 | 0.444 | +0.022 |
| MRR | 0.933 | 0.863 | **−0.070** ✗ |
| nDCG@10 | 0.782 | 0.786 | +0.004 |
| distratores no top-5 | 5 | **8** | **+3** ✗ |

O NIST saiu da invisibilidade: em `CONF-DKR-006`, onde é a fonte principal,
foi de **fora do top-10 para a 4ª posição**. Em `CONF-IMG-002`, de 6ª para 3ª.

### O custo que eu não tinha previsto

Recall subiu, mas **MRR caiu e os distratores aumentaram de 5 para 8**. A causa
é a mesma nos dois casos: no nível de página, o BM25 somava todas as menções ao
tema e isso dava vantagem à fonte normativa. Fatiado, um parágrafo isolado de
uma página distratora que use o termo exato passa a competir de igual para
igual com o melhor trecho da página certa.

Ou seja, o fatiamento troca **precisão no topo** por **cobertura**. É
exatamente o perfil que um reranker corrige, e vira o argumento concreto para
a etapa de reordenação na Fase 4 — agora sustentado por número, não por
expectativa.

### Decisão de parâmetro tomada por medição

O piso de tamanho de chunk começou em 20 tokens e descartava 2,1% das seções.
A amostra dessa faixa mostrou que ali estava o texto **mais normativo** do
corpus — entradas terse de referência:

```
19t  "cap_add specifies additional container capabilities as strings."
16t  "cpu_count defines the number of usable CPUs for service container."
13t  "pids tunes a container's PIDs limit, set as an integer."
```

Piso baixado para 12 tokens (+33 chunks). Abaixo disso o conteúdo é legenda ou
rótulo de navegação.

### Reproduzir

```bash
python scripts/ingerir.py --baixar                      # coleta e ingere
python scripts/medir_baseline.py --chunks corpus/chunks.jsonl
```

## Fase 3 — Índice híbrido

`bge-small-en-v1.5` local (fastembed/ONNX), 384 dimensões. 1.224 chunks
indexados em 270 s de CPU. Fusão por Reciprocal Rank Fusion (k=60).

| modo | R@5 | R@10 | P@5 | MRR | nDCG@10 | distratores |
|---|---|---|---|---|---|---|
| lexical (BM25) | 0.700 | **0.907** | 0.444 | 0.863 | 0.786 | 8 |
| denso | 0.748 | 0.897 | 0.489 | 0.862 | 0.756 | **4** |
| **híbrido (RRF)** | **0.752** ✓ | **0.901** ✓ | **0.489** | **0.877** ✓ | 0.782 ✓ | 5 |

A hipótese da Fase 2 se confirmou: **o denso devolveu a precisão sem custar a
cobertura**. Cada método erra de um jeito diferente e a fusão aproveita os dois:

- **lexical** tem o melhor recall@10 e o pior número de distratores. Ele acha o
  termo exato e se deixa enganar por página que usa o mesmo termo em outro
  sentido;
- **denso** corta os distratores pela metade (8 → 4) porque distingue conceito
  de palavra, mas perde recall onde a resposta depende de um identificador raro;
- **híbrido** fica com o melhor R@5, o melhor MRR e R@10 acima do limiar.

O híbrido passa em todos os limiares **exceto** tolerância zero a distratores.

### Reranker avaliado e descartado

Cross-encoder local (`ms-marco-MiniLM-L-6-v2`) sobre o top-40 do híbrido:

| | híbrido | + reranker |
|---|---|---|
| R@5 | 0.752 | 0.759 |
| P@5 | 0.489 | **0.517** |
| MRR | **0.877** | 0.847 |
| R@10 | **0.901** | 0.898 |
| distratores | 5 | 5 |

Ganha em precisão, **perde em MRR e não resolve nenhum distrator**. Não
justifica o modelo extra nem a latência por request. Provável causa: as
consultas são cadeias densas de termos técnicos escritas para recuperação, não
perguntas naturais — que é o que um cross-encoder treinado em MS MARCO espera.

Fica registrado como resultado negativo medido, não como pendência.

### Os 5 distratores remanescentes

```
CONF-DKR-006 → k8s:images          CONF-SEC-001 → dkr:build-secrets
CONF-K8S-003 → k8s:secrets         CONF-WLD-008 → k8s:volumes
CONF-K8S-004 → k8s:rbac
```

São os pares confundíveis previstos no gabarito, e vários são ambíguos de
verdade no nível de recuperação — token de service account **é** armazenado
como Secret; raiz somente-leitura e volume somente-leitura **usam** o mesmo
termo. O limiar não foi relaxado para o número fechar.

**Mitigação implementada:** os 36 documentos canônicos. Cada resposta de
recuperação traz o texto autoritativo do controle, escrito por nós, sempre —
independentemente do que a busca devolveu. Nos 5 casos acima, o documento
ainda desambigua explicitamente o par confundível.

Exemplo real do `CONF-WLD-008`: a busca devolve `k8s:volumes → Read-only
mounts`, que é o distrator. A âncora afirma a regra certa (raiz do container
somente-leitura) e a seção "Quando não se aplica" avisa que isso **não** é a
mesma coisa que montar um volume como `:ro`.

O limiar de zero distratores continua reprovando o build — corretamente. Ele
mede a qualidade da busca, que é o que se quer melhorar. A âncora garante que
uma falha de busca não vire erro de relatório.

### Reproduzir

```bash
python scripts/indexar.py                   # ~270 s de CPU
python scripts/comparar_retrievers.py
```

## Reproduzir

```bash
python scripts/medir_baseline.py --corpus <diretório com as páginas .html>
```

A Fase 2 substitui o download manual por um job de ingestão versionado.
