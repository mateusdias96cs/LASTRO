"use client";

import { useState } from "react";

/**
 * Bloco com botão de copiar.
 *
 * Usado tanto para a configuração corrigida quanto para a evidência recortada
 * do arquivo enviado — e isso é deliberado: **conteúdo do usuário só aparece
 * dentro de um bloco**, nunca como prosa. Uma linha plantada no arquivo não
 * pode se confundir com o que nós escrevemos.
 */
export function BlocoDeCodigo({
  conteudo,
  rotulo,
  altura,
}: {
  conteudo: string;
  rotulo?: string;
  altura?: number;
}) {
  const [copiado, setCopiado] = useState(false);

  async function copiar() {
    try {
      await navigator.clipboard.writeText(conteudo);
      setCopiado(true);
      setTimeout(() => setCopiado(false), 2000);
    } catch {
      // `clipboard` exige contexto seguro; sem HTTPS o navegador recusa. O
      // texto continua selecionável, então a falha não bloqueia ninguém.
    }
  }

  return (
    <div style={{ border: "1px solid var(--linha-2)", background: "var(--fundo-2)" }}>
      <div
        className="flex items-center justify-between px-3.5 py-2"
        style={{ borderBottom: "1px solid var(--linha-2)" }}
      >
        <span style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--texto-3)" }}>
          {rotulo}
        </span>
        <button
          type="button"
          onClick={copiar}
          className="px-2.5 py-0.5"
          style={{
            fontFamily: "var(--mono)",
            fontSize: 11,
            color: copiado ? "var(--acento)" : "#C4CFD4",
            border: "1px solid var(--borda)",
          }}
        >
          {copiado ? "copiado" : "copiar"}
        </button>
      </div>
      <pre
        className="rolagem-fina overflow-auto px-4 py-3.5"
        style={{
          fontFamily: "var(--mono)",
          fontSize: 11.5,
          lineHeight: 1.75,
          color: "#a9bcc3",
          maxHeight: altura,
          margin: 0,
        }}
      >
        <code>{conteudo}</code>
      </pre>
    </div>
  );
}
