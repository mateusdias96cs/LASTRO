import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "Conformidade — revisão de segurança para Docker e Kubernetes",
  description:
    "Envie um Dockerfile, docker-compose ou manifesto do Kubernetes e receba a " +
    "configuração corrigida, pronta para usar, com a auditoria do que mudou.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR">
      <body className="min-h-screen bg-slate-50 text-slate-900 antialiased">{children}</body>
    </html>
  );
}
