"use client";

import { useState } from "react";

import { arquivoDeTexto } from "@/lib/api";
import type { Idioma } from "@/lib/idioma";

const EXEMPLO = `services:
  api:
    image: minhaapp:latest
    privileged: true
    ports:
      - "5432:5432"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock`;

type Aba = "colar" | "arquivo";

/**
 * Entrada: colar ou subir arquivo. Os dois caminhos viram o mesmo `File` e
 * seguem pelo mesmo POST — dois caminhos de request para o mesmo efeito seriam
 * dois lugares para corrigir quando algo mudar.
 */
export function Envio({
  aoEnviar,
  ocupado,
  lang,
}: {
  aoEnviar: (arquivo: File, contexto: string) => void;
  ocupado: boolean;
  lang: Idioma;
}) {
  const [aba, setAba] = useState<Aba>("colar");
  const [texto, setTexto] = useState("");
  const [nome, setNome] = useState("compose.yaml");
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [contexto, setContexto] = useState("");

  const podeEnviar = aba === "colar" ? texto.trim().length > 0 : arquivo !== null;
  const t = (pt: string, en: string) => (lang === "pt" ? pt : en);

  function enviar(evento: React.FormEvent) {
    evento.preventDefault();
    if (!podeEnviar || ocupado) return;
    const alvo = aba === "colar" ? arquivoDeTexto(texto, nome) : arquivo;
    if (alvo) aoEnviar(alvo, contexto);
  }

  return (
    <form
      onSubmit={enviar}
      style={{ background: "var(--fundo-2)", boxShadow: "0 24px 60px -24px rgba(0,0,0,.6)" }}
    >
      <div className="flex" style={{ borderBottom: "1px solid var(--linha-2)" }}>
        {(["colar", "arquivo"] as Aba[]).map((opcao) => {
          const ativa = aba === opcao;
          return (
            <button
              key={opcao}
              type="button"
              onClick={() => setAba(opcao)}
              className="px-5 py-3 text-[13px]"
              style={{
                color: ativa ? "var(--texto)" : "var(--texto-3)",
                fontWeight: ativa ? 500 : 400,
                borderBottom: ativa ? "2px solid var(--acento)" : "2px solid transparent",
                marginBottom: -1,
              }}
            >
              {opcao === "colar"
                ? t("Colar configuração", "Paste config")
                : t("Enviar arquivo", "Upload file")}
            </button>
          );
        })}
      </div>

      <div className="px-5 py-[18px]">
        {aba === "colar" ? (
          <>
            <textarea
              value={texto}
              onChange={(e) => setTexto(e.target.value)}
              placeholder={EXEMPLO}
              rows={10}
              spellCheck={false}
              aria-label={t("Conteúdo da configuração", "Configuration content")}
              className="rolagem-fina w-full resize-y px-[18px] py-4 outline-none"
              style={{
                background: "var(--fundo)",
                border: "1px solid #16333d",
                fontFamily: "var(--mono)",
                fontSize: 12.5,
                lineHeight: 1.7,
                color: "#8fa6ae",
              }}
            />
            <div className="mt-3.5 flex items-center gap-2.5">
              <label
                htmlFor="ls-nome"
                style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--texto-3)" }}
              >
                {t("Nome", "Name")}
              </label>
              <input
                id="ls-nome"
                value={nome}
                onChange={(e) => setNome(e.target.value)}
                className="px-2.5 py-1 outline-none"
                style={{
                  fontFamily: "var(--mono)",
                  fontSize: 12,
                  color: "#C4CFD4",
                  background: "transparent",
                  border: "1px solid var(--linha-2)",
                }}
              />
              {!texto && (
                <button
                  type="button"
                  onClick={() => setTexto(EXEMPLO)}
                  className="text-[11px] underline"
                  style={{ color: "var(--texto-3)" }}
                >
                  {t("usar um exemplo", "use an example")}
                </button>
              )}
            </div>
          </>
        ) : (
          <div>
            <input
              type="file"
              accept=".yaml,.yml,.json,Dockerfile,.dockerfile,text/*"
              onChange={(e) => setArquivo(e.target.files?.[0] ?? null)}
              className="block w-full text-sm file:mr-3 file:cursor-pointer file:border-0
                         file:px-4 file:py-2 file:text-sm"
              style={{ color: "var(--texto-2)" }}
            />
            <p className="mt-2 text-[11px]" style={{ color: "var(--texto-4)" }}>
              {t(
                "Dockerfile, docker-compose.yml ou manifesto do Kubernetes. Até 2 MB.",
                "Dockerfile, docker-compose.yml or Kubernetes manifest. Up to 2 MB.",
              )}
            </p>
          </div>
        )}

        <div className="mt-4">
          <label
            htmlFor="ls-contexto"
            className="mb-1.5 block text-[11px]"
            style={{ color: "var(--texto-3)" }}
          >
            {t("Contexto (opcional)", "Context (optional)")}
          </label>
          <input
            id="ls-contexto"
            value={contexto}
            onChange={(e) => setContexto(e.target.value)}
            placeholder={t(
              "ex.: coletor de log em DaemonSet, precisa ler /var/log do nó",
              "e.g. log collector as a DaemonSet, must read the node's /var/log",
            )}
            className="w-full px-3.5 py-[11px] text-[13px] outline-none"
            style={{
              border: "1px solid var(--linha-2)",
              background: "var(--fundo)",
              color: "var(--texto)",
            }}
          />
          <p className="mt-[7px] text-[11px] leading-relaxed" style={{ color: "var(--texto-4)" }}>
            {t(
              "Descrever a carga permite reconhecer exceções legítimas — um DaemonSet de rede precisa de acessos que uma API comum não precisa.",
              "Describing the workload lets it recognize legitimate exceptions — a network DaemonSet needs access a plain API does not.",
            )}
          </p>
        </div>

        <button
          type="submit"
          disabled={!podeEnviar || ocupado}
          className="mt-[18px] px-6 py-3 text-[13.5px] font-semibold transition-colors"
          style={{
            background: podeEnviar && !ocupado ? "var(--acento-forte)" : "#1c3b47",
            color: podeEnviar && !ocupado ? "var(--fundo)" : "var(--texto-4)",
            cursor: podeEnviar && !ocupado ? "pointer" : "not-allowed",
          }}
        >
          {ocupado
            ? t("Analisando…", "Analyzing…")
            : t("Analisar configuração", "Analyze configuration")}
        </button>
      </div>
    </form>
  );
}
