# Frontend do Conformidade

Interface para o auditor. **Não tem lógica de negócio**: recebe o arquivo,
manda para a API, mostra a resposta. Toda a análise mora nas quatro camadas do
backend.

## Rodar local

```bash
cp .env.example .env.local     # aponte NEXT_PUBLIC_API_URL para a sua API
npm install
npm run dev                    # http://localhost:3000
```

Com a API rodando local em `http://localhost:8000`, o CORS já libera
`localhost:3000` por padrão, não precisa configurar nada.

## Três coisas que não são óbvias

**CORS é do backend.** Frontend e API moram em domínios diferentes, e o
navegador bloqueia a chamada a menos que a API declare a origem. Em produção,
defina no Container App da API:

```
CONFORMIDADE_CORS_ORIGINS=https://ca-web-<sufixo>.<região>.azurecontainerapps.io
```

Sem isso a chamada falha, e falha do jeito mais confuso possível: o navegador
esconde a resposta e o erro chega como falha de rede genérica.

**A URL da API é fixada no build.** Next embute `NEXT_PUBLIC_*` no bundle que
roda no navegador. Trocar a variável no Container App **não** tem efeito:
precisa reconstruir a imagem com `--build-arg NEXT_PUBLIC_API_URL=...`.

**A primeira análise é lenta.** A API roda com `minReplicas: 0`; depois de
ociosa, precisa acordar. O cliente usa timeout de 60s e avisa na tela a partir
de 4s. Ver o comentário no topo de `src/lib/api.ts`.

## Estrutura

```
src/lib/contratos.ts    tipos espelhando RespostaAuditoria (Pydantic)
src/lib/api.ts          único lugar que sabe que existe rede
src/componentes/        Envio, Carregando, Erro, Resultado, BlocoDeCodigo
src/app/page.tsx        máquina de estados da tela
```
