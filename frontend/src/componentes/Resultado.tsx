"use client";

import { useState } from "react";

import { BlocoDeCodigo } from "@/componentes/BlocoDeCodigo";
import { type Achado, type Auditoria, agruparPorSeveridade } from "@/lib/contratos";
import { type Idioma, tr } from "@/lib/idioma";

/**
 * A saída, na ordem em que serve a quem não é especialista.
 *
 *   1  a configuração corrigida, inteira, pronta para substituir o original
 *   2  o que depende de uma decisão que só quem enviou pode tomar
 *   3  a auditoria, por risco, expansível
 *
 * A ordem é a decisão de desenho mais importante aqui, e é a mesma do design:
 * o arquivo pronto primeiro, a prova depois. Relatório de segurança costuma
 * abrir com a lista de problemas; quem não é da área lê metade e fecha.
 */

const RISCO: Record<string, { rotulo: [string, string]; barra: number; cor: string }> = {
  critical: { rotulo: ["crítico", "critical"], barra: 22, cor: "#C25A2C" },
  high: { rotulo: ["alto", "high"], barra: 18, cor: "#a85a30" },
  medium: { rotulo: ["médio", "medium"], barra: 15, cor: "#8a6a56" },
  low: { rotulo: ["baixo", "low"], barra: 10, cor: "#4d616a" },
  info: { rotulo: ["informativo", "info"], barra: 8, cor: "#3a5561" },
};

export function Resultado({
  auditoria,
  aoRecomecar,
  lang,
}: {
  auditoria: Auditoria;
  aoRecomecar: () => void;
  lang: Idioma;
}) {
  const manuais = Object.entries(auditoria.dependem_de_voce);
  const grupos = agruparPorSeveridade(auditoria.achados);

  return (
    <div className="flex flex-col gap-14">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div
            className="mb-3 text-[11px] uppercase tracking-[0.3em]"
            style={{ fontFamily: "var(--mono)", color: "var(--texto-3)" }}
          >
            {tr(lang, "Resultado", "Result")}
          </div>
          <h2
            className="m-0 text-[clamp(26px,3.4vw,42px)] font-medium leading-tight"
            style={{ fontFamily: "var(--serif)" }}
          >
            {auditoria.total_de_problemas === 0
              ? tr(lang, "Nada a corrigir.", "Nothing to fix.")
              : tr(
                  lang,
                  `${auditoria.total_de_problemas} apontamentos em `,
                  `${auditoria.total_de_problemas} findings in `,
                )}
            {auditoria.total_de_problemas > 0 && (
              <span style={{ fontFamily: "var(--mono)", fontSize: "0.5em", color: "var(--acento)" }}>
                {auditoria.arquivo}
              </span>
            )}
          </h2>
          <p className="mt-2 text-sm" style={{ color: "var(--texto-2)" }}>
            {auditoria.corrigidos_automaticamente.length}{" "}
            {tr(lang, "corrigidos automaticamente", "fixed automatically")}
            {manuais.length > 0 &&
              ` · ${manuais.length} ${tr(lang, "dependem de você", "depend on you")}`}
          </p>
        </div>
        <button
          type="button"
          onClick={aoRecomecar}
          className="px-4 py-2 text-sm"
          style={{ border: "1px solid var(--borda)", color: "var(--texto-2)" }}
        >
          {tr(lang, "Analisar outro", "Analyze another")}
        </button>
      </header>

      <AvisoDeCobertura auditoria={auditoria} lang={lang} />

      {/* ------------------------------------------------- 1. o que fazer */}
      <section>
        <Rotulo numero="1" texto={tr(lang, "Sua configuração corrigida", "Your corrected configuration")} />
        <p className="mb-3 text-sm" style={{ color: "var(--texto-2)" }}>
          {tr(lang, "Substitua o arquivo original por este:", "Replace the original file with this:")}
        </p>
        <BlocoDeCodigo
          conteudo={auditoria.configuracao_corrigida}
          rotulo={auditoria.arquivo}
          altura={460}
        />
        {auditoria.formato !== "dockerfile" && (
          <p className="mt-2 text-[11.5px]" style={{ color: "var(--texto-4)" }}>
            {tr(
              lang,
              "O arquivo foi reescrito a partir da estrutura, então comentários e a ordem original das chaves não são preservados. O conteúdo é equivalente.",
              "The file was rewritten from its structure, so comments and the original key order are not preserved. The content is equivalent.",
            )}
          </p>
        )}
      </section>

      {/* --------------------------------------- 2. decisão do usuário */}
      {manuais.length > 0 && (
        <section>
          <Rotulo numero="2" texto={tr(lang, "O que depende de você", "What depends on you")} />
          <p className="mb-4 text-sm" style={{ color: "var(--texto-2)" }}>
            {tr(
              lang,
              "Não aplicamos estes automaticamente porque um valor inventado deixaria o arquivo válido e quebrado.",
              "We did not apply these automatically: an invented value would leave the file valid and broken.",
            )}
          </p>
          <ul className="flex flex-col gap-3">
            {manuais.map(([controlId, motivo]) => {
              const achado = auditoria.achados.find((a) => a.control_id === controlId);
              return (
                <li key={controlId} className="p-4" style={{ border: "1px solid var(--linha-2)" }}>
                  <p className="font-medium" style={{ color: "var(--texto)" }}>
                    {achado?.titulo ?? controlId}
                  </p>
                  <p className="mt-1 text-sm" style={{ color: "var(--texto-2)" }}>
                    {motivo}
                  </p>
                  {achado?.correcao && (
                    <div className="mt-3">
                      <BlocoDeCodigo
                        conteudo={achado.correcao}
                        rotulo={tr(lang, "modelo", "template")}
                      />
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
        <section>
          <Rotulo
            numero={manuais.length > 0 ? "3" : "2"}
            texto={tr(lang, "Auditoria", "Audit")}
          />
          <div className="flex flex-col gap-7">
            {grupos.map(([severidade, achados]) => (
              <div key={severidade}>
                <div
                  className="mb-2 text-[10.5px] uppercase tracking-[0.22em]"
                  style={{ fontFamily: "var(--mono)", color: "var(--texto-3)" }}
                >
                  {tr(lang, "risco", "risk")} {RISCO[severidade]?.rotulo[lang === "pt" ? 0 : 1]} ·{" "}
                  {achados.length}
                </div>
                <div className="flex flex-col">
                  {achados.map((achado, i) => (
                    <ItemDeAuditoria
                      key={achado.control_id}
                      achado={achado}
                      lang={lang}
                      primeiro={i === 0}
                    />
                  ))}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function Rotulo({ numero, texto }: { numero: string; texto: string }) {
  return (
    <div
      className="mb-2.5 text-[10.5px] uppercase tracking-[0.22em]"
      style={{ fontFamily: "var(--mono)", color: "var(--texto-3)" }}
    >
      {numero} · {texto}
    </div>
  );
}

/**
 * Quanto da análise teve contextualização de IA.
 *
 * Três estados, não dois. A degradação é parcial (o deployment tem limite de
 * requisições por minuto), então "3 de 9" é a informação honesta, e um aviso
 * binário seria enganoso nas duas direções. Em todos os casos vale a mesma
 * ressalva: **a configuração corrigida não depende disso.**
 */
function AvisoDeCobertura({ auditoria, lang }: { auditoria: Auditoria; lang: Idioma }) {
  const total = auditoria.achados.length;
  const comIa = auditoria.explicados_por_ia;
  if (total === 0 || comIa === total) return null;
  const parcial = comIa > 0;

  return (
    <p
      className="p-3.5 text-xs leading-relaxed"
      style={{
        border: `1px solid ${parcial ? "#6b5417" : "var(--linha-2)"}`,
        background: parcial ? "#16130b" : "var(--fundo-2)",
        color: parcial ? "#d8c9a8" : "var(--texto-2)",
      }}
    >
      {parcial
        ? tr(
            lang,
            `${comIa} de ${total} apontamentos receberam contextualização por IA. Os demais usam as explicações do catálogo de controles.`,
            `${comIa} of ${total} findings got AI contextualization. The rest use the control catalog's explanations.`,
          )
        : tr(
            lang,
            "As explicações abaixo vêm do catálogo de controles, não da IA.",
            "The explanations below come from the control catalog, not from AI.",
          )}{" "}
      <strong>
        {tr(
          lang,
          "A configuração corrigida é a mesma de qualquer forma",
          "The corrected configuration is the same either way",
        )}
      </strong>:{" "}
      {tr(lang, "ela não depende da camada de IA.", "it does not depend on the AI layer.")}
      {auditoria.motivo_sem_ia && (
        <span
          className="mt-1.5 block opacity-70"
          style={{ fontFamily: "var(--mono)", fontSize: 10.5 }}
        >
          {auditoria.motivo_sem_ia}
        </span>
      )}
    </p>
  );
}

function ItemDeAuditoria({
  achado,
  lang,
  primeiro,
}: {
  achado: Achado;
  lang: Idioma;
  primeiro: boolean;
}) {
  const [aberto, setAberto] = useState(false);
  const risco = RISCO[achado.severidade] ?? RISCO.low!;

  return (
    <div
      style={{
        border: "1px solid var(--linha-2)",
        borderTop: primeiro ? "1px solid var(--linha-2)" : "none",
        background: aberto ? "var(--fundo-2)" : "transparent",
      }}
    >
      <button
        type="button"
        onClick={() => setAberto((v) => !v)}
        aria-expanded={aberto}
        className="flex w-full items-center justify-between gap-3 px-4 py-3.5 text-left"
      >
        <span className="text-[13.5px]" style={{ color: aberto ? "var(--texto)" : "#C4CFD4" }}>
          {achado.titulo}
        </span>
        <span
          className="flex shrink-0 items-center gap-2.5"
          style={{ fontFamily: "var(--mono)", fontSize: 10.5, color: "var(--texto-3)" }}
        >
          {achado.corrigido_automaticamente && (
            <span
              style={{ color: "var(--acento)" }}
              title={tr(lang, "corrigido automaticamente", "fixed automatically")}
            >
              ✓
            </span>
          )}
          {achado.explicado_por_ia && (
            <span
              style={{ color: "var(--acento)" }}
              title={tr(lang, "explicado por IA", "AI-explained")}
            >
              ✦
            </span>
          )}
          <span>{achado.control_id}</span>
          <span
            style={{
              display: "inline-block",
              width: risco.barra,
              height: 6,
              background: risco.cor,
            }}
            aria-label={risco.rotulo[lang === "pt" ? 0 : 1]}
          />
          <span aria-hidden>{aberto ? "−" : "+"}</span>
        </span>
      </button>

      {aberto && (
        <div
          className="flex flex-col gap-3.5 px-4 py-4"
          style={{ borderTop: "1px solid var(--linha)" }}
        >
          {achado.onde && (
            <div style={{ fontFamily: "var(--mono)", fontSize: 11.5, color: "#8fa6ae" }}>
              {tr(lang, "Em", "In")} {achado.onde}
            </div>
          )}

          {achado.evidencia && (
            <div>
              <div className="mb-1.5 text-[10.5px]" style={{ color: "var(--texto-3)" }}>
                {tr(lang, "Trecho do seu arquivo", "From your file")}
              </div>
              {/* Conteúdo do usuário: sempre em bloco, nunca como prosa. */}
              <div
                className="px-3.5 py-2.5"
                style={{
                  border: "1px solid var(--linha-2)",
                  background: "var(--fundo)",
                  fontFamily: "var(--mono)",
                  fontSize: 11.5,
                  color: "var(--acento)",
                }}
              >
                {achado.evidencia}
              </div>
            </div>
          )}

          <p className="m-0 text-[13.5px] leading-relaxed" style={{ color: "#c4cfd4" }}>
            {achado.explicacao}
          </p>

          {achado.citacoes.length > 0 && (
            <div>
              <div
                className="mb-1.5 text-[10.5px] font-medium"
                style={{ color: "var(--texto-2)" }}
              >
                {tr(lang, "Fonte oficial", "Official source")}
              </div>
              {achado.citacoes.map((citacao, i) => (
                <blockquote
                  key={i}
                  className="m-0 mb-2 pl-3"
                  style={{
                    borderLeft: "2px solid #6b3417",
                    fontFamily: "var(--serif)",
                    fontStyle: "italic",
                    fontSize: 15,
                    lineHeight: 1.5,
                    color: "var(--texto-2)",
                  }}
                >
                  “{citacao.trecho}”
                  {citacao.url && (
                    <a
                      href={citacao.url}
                      target="_blank"
                      rel="noreferrer noopener"
                      className="ml-2"
                      style={{ fontFamily: "var(--sans)", fontStyle: "normal", fontSize: 11 }}
                    >
                      {tr(lang, "ver fonte", "view source")}
                    </a>
                  )}
                </blockquote>
              ))}
            </div>
          )}

          {achado.aviso_de_respaldo && (
            <p
              className="m-0 p-2.5 text-[11.5px]"
              style={{
                border: "1px solid var(--linha-2)",
                background: "var(--fundo)",
                color: "var(--texto-3)",
              }}
            >
              {achado.aviso_de_respaldo}
            </p>
          )}

          {achado.ressalvas.length > 0 && (
            <details>
              <summary className="cursor-pointer text-[11px]" style={{ color: "var(--texto-4)" }}>
                {tr(
                  lang,
                  "O verificador automático ajustou esta análise",
                  "The automatic verifier adjusted this analysis",
                )}
              </summary>
              <ul className="mt-1.5">
                {achado.ressalvas.map((r, i) => (
                  <li
                    key={i}
                    style={{ fontFamily: "var(--mono)", fontSize: 10.5, color: "var(--texto-4)" }}
                  >
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
