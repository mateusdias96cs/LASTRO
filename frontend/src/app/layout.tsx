import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "Lastro — conformidade Docker & Kubernetes",
  description:
    "Envie um Dockerfile, docker-compose ou manifesto do Kubernetes e receba a " +
    "configuração corrigida, pronta para copiar, com a fonte oficial atrás de cada apontamento.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR">
      <head>
        {/* Fontes do Google via <link> e não `next/font`: o build da imagem
            roda sem rede, e `next/font` baixa no build. Preconnect reduz o
            custo do carregamento em runtime. */}
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,400;0,500;0,600;1,400;1,500;1,600&family=Inter+Tight:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
