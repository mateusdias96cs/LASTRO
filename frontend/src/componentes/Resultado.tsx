"use client";

import { useState } from "react";

import { BlocoDeCodigo } from "@/componentes/BlocoDeCodigo";
import {
  type Achado,
  type Auditoria,
  LINGUAGEM,
  ROTULO_SEVERIDADE,
  agruparPorSeveridade,
} from "@/lib/contratos";

/**
 * A saída, na ordem em que serve a quem não é especialista.
 *
 *   1  a configuração corrigida, inteira, pronta para substituir o original
 *   2  o que depende de uma decisão que só quem enviou pode tomar
 *   3  a auditoria, agrupada por risco e expansível
 *
 * A ordem é a decisão mais importante deste componente. Relatório de segurança
 * costuma abrir com a lista de achados e deixar o conserto no fim; quem não é
 * da área lê metade, não entende, e fecha. Começar pelo arquivo pronto entrega
 * o valor na primeira tela e deixa a explicação para quem quiser.
 */

const CORES: Record<string, string> = {
  critical: "bg-red-100 text-red-900 border-red-200",
  high: "bg-orange-100 text-orange-900 border-orange-200",
  medium: "bg-amber-100 text-amber-900 border-amber-200",
  low: "bg-slate-100 text-slate-700 border-slate-200",
  info: "bg-slate-100 text-slate-600 border-slate-200",
};

export function Resultado({ auditoria, aoRecomecar }: { auditoria: Auditoria; aoRecomecar: () => void }) {
  const linguagem = LINGUAGEM[auditoria.formato] ?? "yaml";
  const manuais = Object.entries(auditoria.dependem_de_voce);
  const grupos = agruparPorSeveridade(auditoria.achados);

  return (
    <div className="space-y-10">
      <header className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-medium text-slate-900">
            {auditoria.total_de_problemas === 0
              ? "Nenhum problema encontrado"
              : `${auditoria.total_de_problemas} problema(s) em ${auditoria.arquivo}`}
          </h2>
          <p className="mt-1 text-sm text-slate-600">
            {auditoria.corrigidos_automaticamente.length} corrigido(s) automaticamente
            {manuais.length > 0 && ` · ${manuais.length} dependem de você`}
          </p>
        </div>
        <button
          type="button"
          onClick={aoRecomecar}
          className="shrink-0 rounded-md border border-slate-300 px-3 py-1.5 text-sm
                     text-slate-700 hover:bg-slate-50"
        >
          Analisar outro
        </button>
      </header>

      {!auditoria.com_analise && (
        <p className="rounded-md border border-slate-200 bg-slate-50 p-3 text-xs text-slate-600">
          A contextualização por IA não estava disponível nesta análise. As explicações vêm
          do catálogo de controles, que é determinístico — a configuração corrigida é a
          mesma de qualquer forma.
        </p>
      )}

      {/* ---------------------------------------------- 1. o que fazer */}
      <section className="space-y-3">
        <h3 className="text-sm font-medium uppercase tracking-wide text-slate-500">
          1. Sua configuração corrigida
        </h3>
        <p className="text-sm text-slate-600">Substitua o arquivo original por este:</p>
        <BlocoDeCodigo
          conteudo={auditoria.configuracao_corrigida}
          linguagem={linguagem}
          rotulo={auditoria.arquivo}
        />
        {auditoria.formato !== "dockerfile" && (
          <p className="text-xs text-slate-500">
            O arquivo foi reescrito a partir da estrutura, então comentários e a ordem
            original das chaves não são preservados. O conteúdo é equivalente.
          </p>
        )}
      </section>

      {/* --------------------------------------- 2. decisão do usuário */}
      {manuais.length > 0 && (
        <section className="space-y-3">
          <h3 className="text-sm font-medium uppercase tracking-wide text-slate-500">
            2. O que depende de você
          </h3>
          <p className="text-sm text-slate-600">
            Não aplicamos estes automaticamente porque um valor inventado deixaria o
            arquivo válido e quebrado.
          </p>
          <ul className="space-y-3">
            {manuais.map(([controlId, motivo]) => {
              const achado = auditoria.achados.find((a) => a.control_id === controlId);
              return (
                <li key={controlId} className="rounded-lg border border-slate-200 p-4">
                  <p className="font-medium text-slate-900">{achado?.titulo ?? controlId}</p>
                  <p className="mt-1 text-sm text-slate-600">{motivo}</p>
                  {achado?.correcao && (
                    <div className="mt-3">
                      <p className="mb-1 text-xs text-slate-500">
                        Modelo do que a linha deve virar:
                      </p>
                      <BlocoDeCodigo conteudo={achado.correcao} linguagem={linguagem} />
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        </section>
      )}

      {/* ------------------------------------------------ 3. auditoria */}
      {grupos.length > 0 && (
        <section className="space-y-3">
          <h3 className="text-sm font-medium uppercase tracking-wide text-slate-500">
            {manuais.length > 0 ? "3." : "2."} Auditoria
          </h3>
          {grupos.map(([severidade, achados]) => (
            <div key={severidade} className="space-y-2">
              <p className="text-xs uppercase tracking-wide text-slate-400">
                risco {ROTULO_SEVERIDADE[severidade]} · {achados.length}
              </p>
              {achados.map((achado) => (
                <ItemDeAuditoria key={achado.control_id} achado={achado} linguagem={linguagem} />
              ))}
            </div>
          ))}
        </section>
      )}
    </div>
  );
}

function ItemDeAuditoria({ achado, linguagem }: { achado: Achado; linguagem: string }) {
  const [aberto, setAberto] = useState(false);

  return (
    <div className={`rounded-lg border ${CORES[achado.severidade] ?? CORES.low}`}>
      <button
        type="button"
        onClick={() => setAberto((v) => !v)}
        aria-expanded={aberto}
        className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left"
      >
        <span className="text-sm font-medium">{achado.titulo}</span>
        <span className="flex shrink-0 items-center gap-2 text-xs">
          {achado.corrigido_automaticamente && <span title="corrigido automaticamente">✓</span>}
          <span className="font-mono opacity-60">{achado.control_id}</span>
          <span aria-hidden>{aberto ? "−" : "+"}</span>
        </span>
      </button>

      {aberto && (
        <div className="space-y-3 border-t border-current/10 bg-white/60 px-4 py-3">
          {achado.onde && (
            <p className="text-xs text-slate-600">
              Em <code className="font-mono">{achado.onde}</code>
            </p>
          )}

          {achado.evidencia && (
            <div>
              <p className="mb-1 text-xs text-slate-500">Trecho encontrado no seu arquivo:</p>
              {/* Conteúdo do usuário: sempre em bloco, nunca como prosa. */}
              <BlocoDeCodigo conteudo={achado.evidencia} rotulo="do seu arquivo" />
            </div>
          )}

          <p className="text-sm text-slate-700">{achado.explicacao}</p>

          {achado.citacoes.length > 0 && (
            <div className="space-y-2">
              <p className="text-xs font-medium text-slate-600">Fonte oficial</p>
              {achado.citacoes.map((citacao, i) => (
                <blockquote
                  key={i}
                  className="border-l-2 border-slate-300 pl-3 text-xs italic text-slate-600"
                >
                  “{citacao.trecho}”
                  {citacao.url && (
                    <a
                      href={citacao.url}
                      target="_blank"
                      rel="noreferrer noopener"
                      className="ml-1 not-italic underline"
                    >
                      ver fonte
                    </a>
                  )}
                </blockquote>
              ))}
            </div>
          )}

          {achado.aviso_de_respaldo && (
            <p className="rounded border border-slate-200 bg-slate-50 p-2 text-xs text-slate-600">
              {achado.aviso_de_respaldo}
            </p>
          )}

          {achado.ressalvas.length > 0 && (
            <details>
              <summary className="cursor-pointer text-xs text-slate-500">
                O verificador automático ajustou esta análise
              </summary>
              <ul className="mt-1 space-y-1">
                {achado.ressalvas.map((r, i) => (
                  <li key={i} className="font-mono text-xs text-slate-500">
                    {r}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}
    </div>
  );
}
