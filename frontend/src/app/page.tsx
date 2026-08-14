"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { Carregando } from "@/componentes/Carregando";
import { Envio } from "@/componentes/Envio";
import { Erro } from "@/componentes/Erro";
import { Intro } from "@/componentes/Intro";
import { Marca } from "@/componentes/Marca";
import { Resultado } from "@/componentes/Resultado";
import { ErroDaApi } from "@/lib/api";
import type { Auditoria } from "@/lib/contratos";
import { type Idioma, tr } from "@/lib/idioma";
import { PROGRESSO_INICIAL, auditarComProgresso, type EstadoDoProgresso } from "@/lib/stream";

/**
 * Máquina de estados da tela.
 *
 * Quatro estados explícitos em vez de booleanos soltos: com
 * `carregando`/`erro`/`dados` é possível representar o impossível — carregando
 * e com erro ao mesmo tempo — e a tela acaba mostrando duas coisas ou nenhuma.
 */
type Estado =
  | { nome: "inicial" }
  | { nome: "analisando"; progresso: EstadoDoProgresso }
  | { nome: "pronto"; auditoria: Auditoria }
  | { nome: "erro"; erro: ErroDaApi };

const SECOES = [
  { id: "ls-envio", pt: "Enviar", en: "Analyze" },
  { id: "ls-como", pt: "Como funciona", en: "How it works" },
  { id: "ls-relatorio", pt: "Relatório", en: "Report" },
  { id: "ls-fontes", pt: "Fontes", en: "Sources" },
];

export default function Pagina() {
  const [lang, setLang] = useState<Idioma>("pt");
  const [introVisivel, setIntroVisivel] = useState(true);
  const [estado, setEstado] = useState<Estado>({ nome: "inicial" });
  const painel = useRef<HTMLDivElement>(null);

  const t = useCallback((pt: string, en: string) => tr(lang, pt, en), [lang]);

  // Revela as seções conforme entram na viewport. `IntersectionObserver` em vez
  // de escutar scroll: o navegador faz o cálculo fora da thread principal.
  useEffect(() => {
    const io = new IntersectionObserver(
      (entradas) => {
        entradas.forEach((e) => {
          if (e.isIntersecting) e.target.classList.add("in");
        });
      },
      { threshold: 0.12 },
    );
    document.querySelectorAll(".reveal").forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, []);

  async function analisar(arquivo: File, contexto: string) {
    setEstado({ nome: "analisando", progresso: PROGRESSO_INICIAL });
    painel.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    try {
      const auditoria = await auditarComProgresso(arquivo, {
        contexto,
        aoProgredir: (progresso) =>
          setEstado((atual) => (atual.nome === "analisando" ? { ...atual, progresso } : atual)),
      });
      setEstado({ nome: "pronto", auditoria });
    } catch (erro) {
      setEstado({
        nome: "erro",
        erro:
          erro instanceof ErroDaApi
            ? erro
            : new ErroDaApi("servidor", t("Algo inesperado aconteceu.", "Something went wrong.")),
      });
    }
  }

  return (
    <div className={`lang-${lang}`}>
      {introVisivel && <Intro aoTerminar={() => setIntroVisivel(false)} />}

      {/* ------------------------------------------------------------ NAV */}
      <nav
        className="fixed inset-x-0 top-0 z-50 flex h-16 items-center justify-between
                   px-[clamp(20px,5vw,64px)]"
        style={{
          background: "rgba(6,20,27,.82)",
          backdropFilter: "blur(8px)",
          borderBottom: "1px solid var(--linha)",
        }}
      >
        <a href="#ls-hero" className="flex items-center gap-3">
          <Marca id="ls-navmark" tamanho={30} />
          <span
            style={{
              fontFamily: "var(--serif)",
              fontWeight: 500,
              fontSize: 22,
              letterSpacing: ".22em",
              color: "var(--texto)",
            }}
          >
            LASTRO
          </span>
        </a>
        <div className="flex items-center gap-[clamp(14px,2.4vw,34px)] text-[12.5px]">
          {SECOES.map((s) => (
            <a key={s.id} href={`#${s.id}`} className="hidden sm:inline" style={{ color: "var(--texto-2)" }}>
              {t(s.pt, s.en)}
            </a>
          ))}
          <span
            className="inline-flex items-center gap-2 pl-[clamp(14px,2vw,24px)]"
            style={{ fontFamily: "var(--mono)", fontSize: 11, borderLeft: "1px solid var(--borda)" }}
          >
            {(["pt", "en"] as Idioma[]).map((l, i) => (
              <span key={l} className="flex items-center gap-2">
                {i === 1 && <span style={{ color: "#3a5561" }}>/</span>}
                <button
                  type="button"
                  onClick={() => setLang(l)}
                  style={{
                    color: lang === l ? "var(--acento)" : "#3a5561",
                    opacity: lang === l ? 1 : 0.5,
                  }}
                >
                  {l.toUpperCase()}
                </button>
              </span>
            ))}
          </span>
        </div>
      </nav>

      {/* ----------------------------------------------------------- HERO */}
      <section
        id="ls-hero"
        className="relative flex min-h-screen flex-col justify-center overflow-hidden
                   px-[clamp(24px,7vw,120px)] py-16"
      >
        <Calado />
        <div className="reveal in max-w-[920px] ml-[clamp(0px,9vw,150px)]">
          <div
            className="mb-8 text-[11px] uppercase tracking-[0.34em]"
            style={{ fontFamily: "var(--mono)", color: "var(--texto-3)" }}
          >
            {t("Conformidade Docker & Kubernetes", "Docker & Kubernetes compliance")}
          </div>
          <h1
            className="m-0 text-[clamp(38px,6.6vw,96px)] font-light leading-[1.02]"
            style={{ letterSpacing: "-.015em" }}
          >
            <span className="block">{t("Analise a sua configuração", "Analyze your")}</span>
            <span className="block font-semibold">
              {t("Docker ou Kubernetes", "Docker or Kubernetes config")}
            </span>
            <span
              className="block"
              style={{
                fontFamily: "var(--serif)",
                fontStyle: "italic",
                fontWeight: 500,
                color: "var(--acento)",
                fontSize: "1.14em",
                letterSpacing: 0,
              }}
            >
              {t("com lastro.", "with lastro.")}
            </span>
          </h1>
          <p
            className="mt-9 max-w-[560px] text-[clamp(15px,1.5vw,18px)] leading-relaxed"
            style={{ color: "var(--texto-2)" }}
          >
            {t(
              "A configuração corrigida, pronta para copiar, e um relatório que cita a fonte oficial atrás de cada afirmação. Nada sem respaldo.",
              "The corrected configuration, ready to copy, and a report that cites the official source behind every claim. Nothing without backing.",
            )}
          </p>
          <a
            href="#ls-envio"
            className="mt-10 inline-block px-6 py-3 text-[13.5px] font-semibold"
            style={{ background: "var(--acento-forte)", color: "var(--fundo)" }}
          >
            {t("Analisar agora", "Analyze now")}
          </a>
        </div>
      </section>

      {/* ---------------------------------------------------------- ENVIO */}
      <section
        id="ls-envio"
        ref={painel}
        className="scroll-mt-16 px-[clamp(24px,7vw,120px)] py-24"
        style={{ borderTop: "1px solid #10262f" }}
      >
        <div className="mx-auto w-full max-w-[1200px]">
          <div
            className="reveal mb-8 text-[11px] uppercase tracking-[0.3em]"
            style={{ fontFamily: "var(--mono)", color: "var(--texto-3)" }}
          >
            01 · {t("Envie", "Submit")}
          </div>

          {estado.nome === "inicial" && (
            <div className="grid items-start gap-[clamp(32px,5vw,72px)] lg:grid-cols-[0.92fr_1.08fr]">
              <div className="reveal in">
                <Envio aoEnviar={analisar} ocupado={false} lang={lang} />
              </div>
              <div className="reveal in">
                <h2
                  className="m-0 mb-5 text-[clamp(26px,3vw,38px)] font-medium leading-tight"
                  style={{ fontFamily: "var(--serif)" }}
                >
                  {t("Cole o YAML, ou", "Paste the YAML, or")}
                  <br />
                  <span style={{ fontStyle: "italic", color: "var(--acento)" }}>
                    {t("envie o arquivo.", "upload the file.")}
                  </span>
                </h2>
                <p className="mb-6 text-[14.5px] leading-relaxed" style={{ color: "var(--texto-2)" }}>
                  {t(
                    "Dois caminhos, uma resposta: a configuração reescrita e segura, mais o relatório de auditoria com severidade e fonte de cada apontamento.",
                    "Two paths, one answer: the rewritten, safe configuration, plus an audit report with a severity and a source for every finding.",
                  )}
                </p>
                <dl className="m-0" style={{ borderTop: "1px solid var(--linha-2)" }}>
                  {[
                    ["Dockerfile", t("multi-stage, USER, HEALTHCHECK", "multi-stage, USER, HEALTHCHECK")],
                    ["compose.yaml", t("ports, volumes, capabilities", "ports, volumes, capabilities")],
                    ["k8s manifest", t("multi-doc, securityContext, CronJob", "multi-doc, securityContext, CronJob")],
                  ].map(([chave, valor]) => (
                    <div
                      key={chave}
                      className="flex items-baseline gap-3.5 py-3"
                      style={{ borderBottom: "1px solid var(--linha)" }}
                    >
                      <dt
                        className="min-w-[96px]"
                        style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--acento)" }}
                      >
                        {chave}
                      </dt>
                      <dd className="m-0 text-[13px]" style={{ color: "var(--texto-2)" }}>
                        {valor}
                      </dd>
                    </div>
                  ))}
                </dl>
                <p className="mt-4 text-[11.5px]" style={{ color: "var(--texto-4)" }}>
                  {t(
                    "Até 2 MB. Segredo detectado é redigido antes de sair.",
                    "Up to 2 MB. Detected secrets are redacted before leaving.",
                  )}
                </p>
              </div>
            </div>
          )}

          {estado.nome === "analisando" && <Carregando progresso={estado.progresso} lang={lang} />}

          {estado.nome === "erro" && (
            <Erro
              erro={estado.erro}
              lang={lang}
              aoTentarDeNovo={() => setEstado({ nome: "inicial" })}
            />
          )}

          {estado.nome === "pronto" && (
            <Resultado
              auditoria={estado.auditoria}
              lang={lang}
              aoRecomecar={() => setEstado({ nome: "inicial" })}
            />
          )}
        </div>
      </section>

      {/* --------------------------------------------------- COMO FUNCIONA */}
      <section
        id="ls-como"
        className="scroll-mt-16 px-[clamp(24px,7vw,120px)] py-24"
        style={{ borderTop: "1px solid #10262f" }}
      >
        <div className="mx-auto w-full max-w-[1200px]">
          <div className="reveal mb-14 max-w-[720px]">
            <div
              className="mb-4 text-[11px] uppercase tracking-[0.3em]"
              style={{ fontFamily: "var(--mono)", color: "var(--texto-3)" }}
            >
              02 · {t("Como funciona", "How it works")}
            </div>
            <h2
              className="m-0 text-[clamp(30px,4vw,52px)] font-medium leading-[1.08]"
              style={{ fontFamily: "var(--serif)" }}
            >
              {t("Quatro camadas, uma", "Four layers, one")}
              <span style={{ fontStyle: "italic", color: "var(--acento)" }}>
                {t(" só afirmação por vez.", " claim at a time.")}
              </span>
            </h2>
          </div>

          <div className="grid gap-[clamp(28px,4vw,68px)] md:grid-cols-2 xl:grid-cols-4">
            {[
              {
                n: "01",
                titulo: t("Determinístico", "Deterministic"),
                texto: t(
                  "Parseia e roda 36 controles fixos. Sem LLM, sem rede: a mesma entrada dá o mesmo relatório, byte a byte.",
                  "Parses and runs 36 fixed controls. No LLM, no network: the same input yields the same report, byte for byte.",
                ),
              },
              {
                n: "02",
                titulo: t("Recuperação", "Retrieval"),
                texto: t(
                  "Âncora canônica mais busca híbrida trazem o documento do controle e os trechos oficiais que o sustentam.",
                  "A canonical anchor plus hybrid search pull the control's document and the official passages backing it.",
                ),
              },
              {
                n: "03",
                destaque: true,
                titulo: t("Análise", "Analysis"),
                texto: t(
                  "Aqui entra a IA. Avalia o contexto que você deu, reconhece exceções legítimas da sua carga e combina cada achado com a fonte que o sustenta.",
                  "This is where AI enters. It weighs the context you gave, recognizes legitimate exceptions, and pairs each finding with its source.",
                ),
              },
              {
                n: "04",
                titulo: t("Crítico", "Critic"),
                texto: t(
                  "Confere cada citação contra a fonte oficial e a coerência do todo. O que não tem lastro não passa.",
                  "Checks every citation against the official source and the coherence of the whole. What lacks backing does not pass.",
                ),
              },
            ].map((c, i) => (
              <div key={c.n} className="reveal" style={{ transitionDelay: `${i * 0.08}s` }}>
                <div
                  className="mb-[-6px] leading-[0.8]"
                  style={{
                    fontFamily: "var(--serif)",
                    fontWeight: 500,
                    fontStyle: c.destaque ? "italic" : "normal",
                    fontSize: c.destaque ? "clamp(84px,9vw,150px)" : "clamp(72px,8vw,128px)",
                    color: c.destaque ? "var(--acento)" : "#16333d",
                  }}
                >
                  {c.n}
                </div>
                <h3
                  className="m-0 mb-3"
                  style={{
                    fontFamily: "var(--serif)",
                    fontStyle: "italic",
                    fontWeight: c.destaque ? 600 : 500,
                    fontSize: c.destaque ? 29 : 22,
                    color: "var(--texto)",
                  }}
                >
                  {c.titulo}
                </h3>
                <p
                  className="m-0 max-w-[30ch] leading-relaxed"
                  style={{
                    fontSize: c.destaque ? 14.5 : 13,
                    color: c.destaque ? "#c4cfd4" : "#8296a0",
                  }}
                >
                  {c.texto}
                </p>
              </div>
            ))}
          </div>

          <p className="reveal mt-8 max-w-[640px] text-[12.5px] leading-relaxed" style={{ color: "#5f727b" }}>
            {t(
              "A detecção e a correção são determinísticas. A explicação usa IA e passa pelo crítico, que confere cada citação contra a fonte.",
              "Detection and correction are deterministic. The explanation uses AI and passes through the critic, which checks each citation against the source.",
            )}
          </p>
        </div>
      </section>

      {/* --------------------------------------------------------- FONTES */}
      <section
        id="ls-fontes"
        className="scroll-mt-16 px-[clamp(24px,7vw,120px)] py-24"
        style={{ borderTop: "1px solid #10262f" }}
      >
        <div className="mx-auto w-full max-w-[1200px]">
          <div className="reveal mb-12 flex flex-wrap items-end justify-between gap-8">
            <div className="max-w-[720px]">
              <div
                className="mb-4 text-[11px] uppercase tracking-[0.3em]"
                style={{ fontFamily: "var(--mono)", color: "var(--texto-3)" }}
              >
                03 · {t("Fontes & respaldo", "Sources & backing")}
              </div>
              <h2
                className="m-0 text-[clamp(30px,4.4vw,56px)] font-medium leading-[1.06]"
                style={{ fontFamily: "var(--serif)" }}
              >
                {t("Nenhuma afirmação", "No claim")}
                <br />
                <span style={{ fontStyle: "italic", color: "var(--acento)" }}>
                  {t("sem lastro.", "without backing.")}
                </span>
              </h2>
            </div>
            <div className="text-right" style={{ fontFamily: "var(--mono)", color: "var(--texto-3)" }}>
              <div className="text-[clamp(28px,3vw,42px)]" style={{ color: "var(--texto)" }}>
                35
              </div>
              <div className="text-[10.5px] uppercase tracking-[0.14em]">
                {t("páginas no corpus", "pages in corpus")}
              </div>
            </div>
          </div>

          <div className="reveal grid gap-[clamp(24px,3.4vw,56px)] sm:grid-cols-2 xl:grid-cols-4">
            {[
              ["Docker", t("Documentação oficial de diretivas e runtime.", "Official docs for directives and runtime.")],
              ["Kubernetes", t("securityContext, políticas de pod.", "securityContext, pod policies.")],
              ["NIST", t("SP 800-190, segurança de contêineres.", "SP 800-190, container security.")],
              ["CIS Benchmark", t("Seções 4 e 5, sob CC BY-NC-SA.", "Sections 4 and 5, under CC BY-NC-SA.")],
            ].map(([nome, desc], i) => (
              <div
                key={nome}
                style={{
                  paddingTop: 22,
                  borderTop: `1px solid ${i === 0 ? "var(--acento)" : "var(--borda)"}`,
                  marginTop: `clamp(0px,${i * 2.2}vw,${i * 34}px)`,
                }}
              >
                <div
                  className="mb-3.5"
                  style={{ fontFamily: "var(--serif)", fontStyle: "italic", fontSize: 24 }}
                >
                  {nome}
                </div>
                <div className="max-w-[24ch] text-[12.5px] leading-relaxed" style={{ color: "#8296a0" }}>
                  {desc}
                </div>
              </div>
            ))}
          </div>

          <div
            className="reveal mt-9 flex flex-wrap gap-x-12 gap-y-6"
            style={{ fontFamily: "var(--mono)", fontSize: 11.5, color: "var(--texto-3)" }}
          >
            <span>
              <span style={{ color: "#C4CFD4" }}>36</span>{" "}
              {t("controles canônicos", "canonical controls")}
            </span>
            <span>
              <span style={{ color: "#C4CFD4" }}>R@10 0,92</span>{" "}
              {t("busca híbrida (RRF)", "hybrid search (RRF)")}
            </span>
            <span>
              <span style={{ color: "#C4CFD4" }}>524</span>{" "}
              {t("testes no portão de qualidade", "tests in the quality gate")}
            </span>
          </div>

          <footer
            className="mt-[clamp(60px,9vh,110px)] flex flex-wrap items-end justify-between gap-6 pt-7"
            style={{ borderTop: "1px solid var(--linha)" }}
          >
            <div className="flex items-center gap-3.5">
              <Marca tamanho={34} />
              <div>
                <div
                  style={{
                    fontFamily: "var(--serif)",
                    fontWeight: 500,
                    fontSize: 20,
                    letterSpacing: ".2em",
                  }}
                >
                  LASTRO
                </div>
                <div className="mt-0.5 text-[11px]" style={{ color: "var(--texto-4)" }}>
                  {t("Conformidade com fundamento.", "Compliance with sound footing.")}
                </div>
              </div>
            </div>
            <p
              className="m-0 max-w-[460px] text-right text-[11.5px] leading-relaxed"
              style={{ color: "var(--texto-4)" }}
            >
              {t(
                "A detecção e a correção são determinísticas. A explicação usa IA e passa por um verificador que confere cada citação contra a fonte oficial.",
                "Detection and correction are deterministic. The explanation uses AI and passes through a verifier that checks each citation against the official source.",
              )}
            </p>
          </footer>
        </div>
      </section>
    </div>
  );
}

/** A régua de calado do hero — a metáfora que dá nome ao produto. */
function Calado() {
  return (
    <div
      className="pointer-events-none absolute left-[clamp(24px,7vw,120px)] top-1/2
                 hidden -translate-y-1/2 lg:block"
      aria-hidden
    >
      <div className="relative h-[320px] w-16">
        <div className="absolute inset-y-0 left-0 w-px" style={{ background: "var(--borda)" }} />
        {[
          [8, 14],
          [24, 9],
          [40, 14],
          [72, 9],
          [88, 14],
        ].map(([topo, largura]) => (
          <div
            key={topo}
            className="absolute left-0 h-px"
            style={{ top: `${topo}%`, width: largura, background: "#385260" }}
          />
        ))}
        <div
          className="absolute left-0 h-0.5"
          style={{ top: "56%", width: 24, background: "var(--acento)" }}
        />
        <div
          className="absolute"
          style={{
            left: 30,
            top: "calc(56% - 8px)",
            fontFamily: "var(--mono)",
            fontSize: 9,
            letterSpacing: ".1em",
            color: "var(--acento)",
          }}
        >
          LWL
        </div>
      </div>
    </div>
  );
}
