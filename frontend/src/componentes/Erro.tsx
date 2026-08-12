import type { ErroDaApi } from "@/lib/api";

/**
 * Falha com nome, causa provável e o que fazer.
 *
 * Um frontend "que funciona" não é o caminho feliz funcionando — é cada modo
 * de falha ter uma tela própria em vez de travar em branco ou despejar erro
 * técnico. O detalhe técnico existe, mas fica no rodapé, para quem for
 * investigar; a mensagem principal é para quem só quer saber se o problema é
 * dele ou nosso.
 */
export function Erro({ erro, aoTentarDeNovo }: { erro: ErroDaApi; aoTentarDeNovo: () => void }) {
  const culpaDoUsuario = erro.tipo === "arquivo_invalido" || erro.tipo === "arquivo_grande";

  return (
    <div
      role="alert"
      className={`rounded-lg border p-6 ${
        culpaDoUsuario ? "border-amber-300 bg-amber-50" : "border-red-300 bg-red-50"
      }`}
    >
      <p className="font-medium text-slate-900">{erro.mensagem}</p>
      {erro.sugestao && <p className="mt-2 text-sm text-slate-700">{erro.sugestao}</p>}

      <button
        type="button"
        onClick={aoTentarDeNovo}
        className="mt-4 rounded-md bg-slate-900 px-4 py-2 text-sm text-white hover:bg-slate-700"
      >
        Tentar de novo
      </button>

      {erro.detalhe && (
        <details className="mt-4">
          <summary className="cursor-pointer text-xs text-slate-500">Detalhe técnico</summary>
          <p className="mt-1 break-words font-mono text-xs text-slate-500">{erro.detalhe}</p>
        </details>
      )}
    </div>
  );
}
