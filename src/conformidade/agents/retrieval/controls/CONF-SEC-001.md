## Afirmação normativa

Credenciais não devem ser declaradas como valor literal em variável de
ambiente. Senhas, tokens, chaves de API e connection strings com senha devem
vir de um gerenciador de segredos ou do mecanismo de segredo do orquestrador.

## Por que importa

Variável de ambiente com segredo vaza por vários caminhos ao mesmo tempo, e
todos são comuns:

- `docker inspect` e `kubectl describe pod` mostram o valor a qualquer pessoa
  com acesso de leitura ao recurso
- processos filhos herdam o ambiente inteiro, muitas vezes sem necessidade
- dump de memória e log de crash frequentemente incluem o ambiente
- bibliotecas de telemetria capturam variáveis de ambiente por padrão
- e o mais frequente de todos: o arquivo com o valor está **versionado no
  repositório**, com todo o histórico de quem o leu

O último é o que transforma um erro de configuração em incidente duradouro:
rotacionar o segredo não apaga o histórico do Git.

## Como corrigir

```yaml
# Kubernetes — referência, não valor
env:
  - name: DB_PASSWORD
    valueFrom:
      secretKeyRef: { name: app-secrets, key: db-password }

# Compose — arquivo de segredo em vez de environment
secrets:
  db_password:
    file: ./secrets/db_password
```

O padrão mais robusto é o sufixo `_FILE`: a aplicação lê o segredo de um
arquivo montado em vez de recebê-lo no ambiente. Em Azure, `DefaultAzureCredential`
com managed identity buscando do Key Vault elimina o segredo estático por completo.

## Quando não se aplica

Valor não sensível cujo nome apenas parece sensível — `AUTH_ENABLED=true`,
`TOKEN_TTL=3600`. Variável terminada em `_FILE`, `_PATH` ou `_URI` aponta para
um segredo, não o contém.
