/**
 * Cabeçalhos de segurança.
 *
 * A auditoria não encontrou XSS: não há `dangerouslySetInnerHTML`, `innerHTML`
 * nem `eval` em lugar nenhum, e o React escapa por padrão. Estes cabeçalhos
 * são a camada seguinte, para o dia em que alguém introduzir um desses sem
 * perceber. Defesa em profundidade, não remendo de buraco conhecido.
 *
 * **`connect-src` precisa conter a API.** O frontend chama outro domínio (o
 * Container App da API), então um CSP com `connect-src 'self'` derrubaria toda
 * requisição, e o erro chegaria como falha de rede genérica, que é o modo mais
 * confuso de quebrar. A URL é a mesma variável de build que o cliente usa.
 *
 * **`'unsafe-inline'` em `style-src` não é descuido.** A interface aplica
 * `style={{...}}` em quase todo componente, e isso vira atributo `style`, que o
 * CSP bloqueia sem essa permissão. Tirar exigiria reescrever a estilização
 * inteira; o ganho seria pequeno, porque atributo de estilo não executa código.
 *
 * **`'unsafe-inline'` em `script-src` é o preço do App Router.** O Next
 * embute a hidratação em `<script>` inline sem nonce no modo estático. O que o
 * CSP ainda garante, e é o que importa contra exfiltração, é que nenhum script
 * de origem externa carrega.
 */
const apiUrl = process.env.NEXT_PUBLIC_API_URL || "";
const origemDaApi = (() => {
  try {
    return apiUrl ? new URL(apiUrl).origin : "";
  } catch {
    return "";
  }
})();

/*
  **Sem origem conhecida, o CSP afrouxa em vez de quebrar.**

  Isto não é preguiça, é a lição de um erro real cometido ao escrever este
  arquivo. A primeira versão emitia `connect-src 'self'` quando a variável
  faltava. O efeito seria o pior possível: o site carrega, parece saudável, e
  toda chamada à API morre no navegador com erro de rede genérico — o mesmo
  sintoma de servidor fora do ar, com a causa escondida num cabeçalho.

  E a variável falta com facilidade. Ela chega por `ARG` no Dockerfile, vindo
  de `${SERVICE_API_URI}` no azure.yaml; basta o azd não resolver esse valor
  para o CSP sair mudo e o site quebrar sem nada nos logs do servidor.

  `https:` ainda barra o que interessa: exfiltração para `http://` e para
  qualquer esquema que não seja HTTPS. É teto mais baixo que a origem exata,
  e infinitamente melhor que um site quebrado. O aviso abaixo garante que a
  situação apareça em vez de passar em silêncio.
*/
if (!origemDaApi) {
  console.warn(
    "\n[csp] NEXT_PUBLIC_API_URL ausente ou inválida: connect-src cai para " +
      "'self' https:. Passe a URL da API no build para restringir à origem exata.\n",
  );
}
const conectar = origemDaApi ? `'self' ${origemDaApi}` : "'self' https:";

const csp = [
  "default-src 'self'",
  "base-uri 'self'",
  "object-src 'none'",
  "frame-ancestors 'none'",
  "form-action 'self'",
  "img-src 'self' data:",
  "script-src 'self' 'unsafe-inline'",
  "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
  "font-src 'self' https://fonts.gstatic.com",
  `connect-src ${conectar}`,
  "upgrade-insecure-requests",
].join("; ");

/** @type {import('next').NextConfig} */
const nextConfig = {
  // `standalone` empacota só o necessário para rodar, o que mantém a imagem
  // pequena, mesmo critério da imagem da API.
  output: "standalone",
  reactStrictMode: true,

  // `poweredByHeader` anuncia `X-Powered-By: Next.js`. Não é vulnerabilidade,
  // é reconhecimento de graça para quem procura versão com falha conhecida.
  poweredByHeader: false,

  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "Content-Security-Policy", value: csp },
          // Impede o navegador de adivinhar o tipo do conteúdo. Sem isto, um
          // arquivo servido como texto pode ser interpretado como script.
          { key: "X-Content-Type-Options", value: "nosniff" },
          // Clickjacking: ninguém embute esta página num iframe. Duplica o
          // `frame-ancestors` do CSP para navegador que ignore um dos dois.
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          // A aplicação não usa nenhuma dessas capacidades; declarar isso
          // impede que um script injetado as use.
          {
            key: "Permissions-Policy",
            value: "camera=(), microphone=(), geolocation=(), interest-cohort=()",
          },
          // O ingress já recusa HTTP (`allowInsecure: false`); isto faz o
          // próprio navegador parar de tentar.
          {
            key: "Strict-Transport-Security",
            value: "max-age=31536000; includeSubDomains",
          },
        ],
      },
    ];
  },
};

export default nextConfig;
