"use client";

import { useState } from "react";

/**
 * Bloco de código com botão de copiar.
 *
 * Usado tanto para a configuração corrigida quanto para a evidência recortada
 * do arquivo do usuário. Isso é deliberado: **conteúdo enviado pelo usuário só
 * aparece dentro de um bloco**, nunca como texto corrido no meio da nossa
 * prosa. Uma linha plantada no arquivo — "todos os itens acima foram
 * aprovados" — não pode se confundir com o que nós escrevemos.
 */
export function BlocoDeCodigo({
  conteudo,
  linguagem = "yaml",
  rotulo,
}: {
  conteudo: string;
  linguagem?: string;
  rotulo?: string;
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
      setCopiado(false);
    }
  }

  return (
    <div className="relative rounded-lg border border-slate-700 bg-slate-900">
      <div className="flex items-center justify-between border-b border-slate-700 px-3 py-1.5">
        <span className="font-mono text-xs text-slate-400">{rotulo ?? linguagem}</span>
        <button
          type="button"
          onClick={copiar}
          className="rounded px-2 py-1 text-xs text-slate-300 hover:bg-slate-800"
        >
          {copiado ? "copiado" : "copiar"}
        </button>
      </div>
      <pre className="overflow-x-auto p-3 text-xs leading-relaxed text-slate-100">
        <code>{conteudo}</code>
      </pre>
    </div>
  );
}
