import type { ErroDaApi } from "@/lib/api";
import type { Idioma } from "@/lib/idioma";

/**
 * Falha com nome, causa provável e o que fazer.
 *
 * O detalhe técnico existe mas fica recolhido: a mensagem principal é para
 * quem só quer saber se o problema é dele ou nosso.
 */
export function Erro({
  erro,
  aoTentarDeNovo,
  lang,
}: {
  erro: ErroDaApi;
  aoTentarDeNovo: () => void;
  lang: Idioma;
}) {
  const culpaDoUsuario = erro.tipo === "arquivo_invalido" || erro.tipo === "arquivo_grande";
  return (
    <div
      role="alert"
      className="p-6"
      style={{
        border: `1px solid ${culpaDoUsuario ? "#6b5417" : "#6b3417"}`,
        background: culpaDoUsuario ? "#16130b" : "#160f0b",
      }}
    >
      <p className="font-medium" style={{ color: "var(--texto)" }}>
        {erro.mensagem}
      </p>
      {erro.sugestao && (
        <p className="mt-2 text-sm" style={{ color: "var(--texto-2)" }}>
          {erro.sugestao}
        </p>
      )}
      <button
        type="button"
        onClick={aoTentarDeNovo}
        className="mt-4 px-5 py-2.5 text-sm font-semibold"
        style={{ background: "var(--acento-forte)", color: "var(--fundo)" }}
      >
        {lang === "pt" ? "Tentar de novo" : "Try again"}
      </button>
      {erro.detalhe && (
        <details className="mt-4">
          <summary className="cursor-pointer text-xs" style={{ color: "var(--texto-4)" }}>
            {lang === "pt" ? "Detalhe técnico" : "Technical detail"}
          </summary>
          <p
            className="mt-1 break-words text-xs"
            style={{ fontFamily: "var(--mono)", color: "var(--texto-4)" }}
          >
            {erro.detalhe}
          </p>
        </details>
      )}
    </div>
  );
}
