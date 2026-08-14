"use client";

import { ETAPAS, ROTULO_ETAPA, type EstadoDoProgresso } from "@/lib/stream";

/**
 * A sonda de calado: as quatro camadas, com o progresso REAL do backend.
 *
 * O design original animava os quatro estágios em oito segundos, distribuídos
 * igualmente. A medição diz outra coisa: as camadas 1, 2 e 4 somam
 * milissegundos e a 3 responde por ~99% do tempo — catorze achados levaram
 * 1m46s, quase tudo nela.
 *
 * Manter a coreografia teria duas consequências ruins. A barra terminaria com
 * o trabalho ainda em curso, e o usuário concluiria que travou. E seria uma
 * mentira sobre o sistema, numa ferramenta cujo argumento inteiro é não
 * afirmar nada sem lastro.
 *
 * A solução não é uma barra mais lenta: é o estágio 3 mostrar contagem real de
 * achados. A tela continua viva durante a espera longa, e o que ela mostra é
 * verdade.
 */
export function Carregando({
  progresso,
  lang,
}: {
  progresso: EstadoDoProgresso;
  lang: "pt" | "en";
}) {
  const indiceAtual = progresso.atual ? ETAPAS.indexOf(progresso.atual) : -1;

  return (
    <div className="flex flex-col items-center gap-10 py-16" role="status" aria-live="polite">
      <div className="text-center">
        <div
          className="text-[11px] uppercase tracking-[0.34em]"
          style={{ fontFamily: "var(--mono)", color: "var(--texto-3)" }}
        >
          {lang === "pt" ? "Rodando os testes" : "Running the checks"}
        </div>
        <div
          className="mt-2.5 text-[clamp(26px,3.4vw,38px)] font-medium"
          style={{ fontFamily: "var(--serif)", color: "var(--texto)" }}
        >
          {lang === "pt" ? "Quatro camadas em curso" : "Four layers in progress"}
        </div>
      </div>

      <div className="flex items-center gap-[clamp(28px,5vw,52px)]">
        <Tubo indiceAtual={indiceAtual} concluidas={progresso.concluidas.size} />

        <ol
          className="flex h-[228px] flex-col-reverse justify-between"
          style={{ fontFamily: "var(--mono)", fontSize: 12 }}
        >
          {ETAPAS.map((etapa, i) => {
            const feita = progresso.concluidas.has(etapa);
            const ativa = progresso.atual === etapa && !feita;
            const cor = ativa ? "var(--acento)" : feita ? "var(--texto-3)" : "#3a5561";
            return (
              <li key={etapa} style={{ color: cor, opacity: ativa || feita ? 1 : 0.35 }}>
                <span>
                  {String(i + 1).padStart(2, "0")} · {ROTULO_ETAPA[etapa][lang]}
                </span>
                {etapa === "analise" && (
                  <div
                    className="mt-[3px] text-[10px] tracking-[0.08em]"
                    style={{ fontFamily: "var(--sans)", color: "#5f727b" }}
                  >
                    {/* A contagem só existe quando há o que contar. Antes
                        disso, o aviso honesto de que esta é a etapa lenta. */}
                    {ativa && progresso.totalDeAchados > 0
                      ? lang === "pt"
                        ? `${progresso.analisados} de ${progresso.totalDeAchados} achados`
                        : `${progresso.analisados} of ${progresso.totalDeAchados} findings`
                      : lang === "pt"
                        ? "IA · pode demorar"
                        : "AI · may take longer"}
                  </div>
                )}
              </li>
            );
          })}
        </ol>
      </div>

      {progresso.atual === "analise" && (
        <p className="max-w-md text-center text-xs" style={{ color: "var(--texto-4)" }}>
          {lang === "pt"
            ? "Cada achado é explicado individualmente e conferido contra a fonte oficial. É a etapa mais demorada — analisar o mesmo arquivo de novo é quase instantâneo."
            : "Each finding is explained individually and checked against the official source. This is the slow step — analyzing the same file again is nearly instant."}
        </p>
      )}
    </div>
  );
}

/** O tubo de sondagem. O preenchimento acompanha as camadas concluídas. */
function Tubo({ indiceAtual, concluidas }: { indiceAtual: number; concluidas: number }) {
  const fracao = Math.min(concluidas / ETAPAS.length, 1);
  const marcas = [180, 124, 66, 22];

  return (
    <svg width="96" height="248" viewBox="0 0 86 248" fill="none" aria-hidden>
      <rect x="30" y="10" width="26" height="228" stroke="var(--borda)" strokeWidth="1.4" />
      <rect
        x="31"
        y="11"
        width="24"
        height="226"
        fill="#0e2a36"
        style={{
          transformOrigin: "bottom",
          transform: `scaleY(${fracao})`,
          transition: "transform .6s cubic-bezier(.2,0,0,1)",
        }}
      />
      <g stroke="#385260" strokeWidth="1.2">
        <path d="M56 180 H70" />
        <path d="M56 124 H70" />
        <path d="M56 66 H70" />
      </g>
      <g strokeWidth="1.4">
        {marcas.map((y, i) => {
          const feita = i < concluidas;
          const ativa = i === indiceAtual && !feita;
          return (
            <path
              key={y}
              d={`M18 ${y} H30`}
              stroke={ativa ? "var(--acento)" : feita ? "var(--texto-3)" : "#3a5561"}
              opacity={ativa || feita ? 1 : 0.35}
              style={{ transition: "stroke .3s, opacity .3s" }}
            />
          );
        })}
      </g>
    </svg>
  );
}
