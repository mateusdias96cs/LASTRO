"use client";

import { useRef, useState } from "react";

import { arquivoDeTexto } from "@/lib/api";

/**
 * Entrada: subir arquivo ou colar texto.
 *
 * Os dois caminhos produzem um `File` e seguem pelo mesmo `POST` multipart. A
 * alternativa seria um endpoint JSON só para texto colado, e aí passariam a
 * existir dois caminhos de request para o mesmo efeito — dois lugares para
 * corrigir quando algo mudar, e duas chances de divergirem.
 *
 * Colar é o caminho mais provável para quem só quer testar rápido, então é a
 * aba inicial.
 */

const EXEMPLO = `services:
  api:
    image: minhaapp:latest
    privileged: true
    ports:
      - "5432:5432"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock`;

type Aba = "colar" | "arquivo";

export function Envio({
  aoEnviar,
  ocupado,
}: {
  aoEnviar: (arquivo: File, contexto: string) => void;
  ocupado: boolean;
}) {
  const [aba, setAba] = useState<Aba>("colar");
  const [texto, setTexto] = useState("");
  const [nome, setNome] = useState("compose.yaml");
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [contexto, setContexto] = useState("");
  const campoArquivo = useRef<HTMLInputElement>(null);

  const podeEnviar = aba === "colar" ? texto.trim().length > 0 : arquivo !== null;

  function enviar(evento: React.FormEvent) {
    evento.preventDefault();
    if (!podeEnviar || ocupado) return;
    const alvo = aba === "colar" ? arquivoDeTexto(texto, nome) : arquivo;
    if (alvo) aoEnviar(alvo, contexto);
  }

  return (
    <form onSubmit={enviar} className="space-y-4">
      <div className="flex gap-1 border-b border-slate-200">
        {(["colar", "arquivo"] as Aba[]).map((opcao) => (
          <button
            key={opcao}
            type="button"
            onClick={() => setAba(opcao)}
            className={`px-4 py-2 text-sm ${
              aba === opcao
                ? "border-b-2 border-slate-900 font-medium text-slate-900"
                : "text-slate-500 hover:text-slate-700"
            }`}
          >
            {opcao === "colar" ? "Colar configuração" : "Enviar arquivo"}
          </button>
        ))}
      </div>

      {aba === "colar" ? (
        <div className="space-y-2">
          <textarea
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            placeholder={EXEMPLO}
            rows={12}
            spellCheck={false}
            className="w-full rounded-lg border border-slate-300 p-3 font-mono text-xs
                       focus:border-slate-500 focus:outline-none"
            aria-label="conteúdo da configuração"
          />
          <div className="flex items-center gap-2">
            <label htmlFor="nome" className="text-xs text-slate-500">
              Nome do arquivo
            </label>
            <input
              id="nome"
              value={nome}
              onChange={(e) => setNome(e.target.value)}
              className="rounded border border-slate-300 px-2 py-1 font-mono text-xs"
            />
            <span className="text-xs text-slate-400">
              usado só para detectar o formato quando o conteúdo for ambíguo
            </span>
          </div>
          {!texto && (
            <button
              type="button"
              onClick={() => setTexto(EXEMPLO)}
              className="text-xs text-slate-600 underline hover:text-slate-900"
            >
              usar um exemplo com problemas
            </button>
          )}
        </div>
      ) : (
        <div>
          <input
            ref={campoArquivo}
            type="file"
            accept=".yaml,.yml,.json,Dockerfile,.dockerfile,text/*"
            onChange={(e) => setArquivo(e.target.files?.[0] ?? null)}
            className="block w-full text-sm text-slate-600 file:mr-3 file:rounded-md
                       file:border-0 file:bg-slate-900 file:px-4 file:py-2 file:text-sm
                       file:text-white hover:file:bg-slate-700"
          />
          <p className="mt-2 text-xs text-slate-500">
            Dockerfile, docker-compose.yml ou manifesto do Kubernetes. Até 2&nbsp;MB.
          </p>
        </div>
      )}

      <div>
        <label htmlFor="contexto" className="text-xs text-slate-500">
          Contexto (opcional)
        </label>
        <input
          id="contexto"
          value={contexto}
          onChange={(e) => setContexto(e.target.value)}
          placeholder="ex.: coletor de log em DaemonSet, precisa ler /var/log do nó"
          className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm
                     focus:border-slate-500 focus:outline-none"
        />
        <p className="mt-1 text-xs text-slate-400">
          Descrever a carga permite reconhecer exceções legítimas — um DaemonSet de rede
          precisa de acessos que uma API comum não precisa.
        </p>
      </div>

      <button
        type="submit"
        disabled={!podeEnviar || ocupado}
        className="rounded-md bg-slate-900 px-5 py-2.5 text-sm font-medium text-white
                   hover:bg-slate-700 disabled:cursor-not-allowed disabled:bg-slate-300"
      >
        {ocupado ? "Analisando…" : "Analisar configuração"}
      </button>
    </form>
  );
}
