"use client";

import { useState } from "react";

import { Carregando } from "@/componentes/Carregando";
import { Envio } from "@/componentes/Envio";
import { Erro } from "@/componentes/Erro";
import { Resultado } from "@/componentes/Resultado";
import { ErroDaApi, auditar } from "@/lib/api";
import type { Auditoria } from "@/lib/contratos";

/**
 * Máquina de estados da tela.
 *
 * Quatro estados explícitos em vez de booleanos soltos (`carregando`, `erro`,
 * `dados`): com booleanos é possível representar o impossível — carregando e
 * com erro ao mesmo tempo — e a tela acaba mostrando duas coisas ou nenhuma.
 */
type Estado =
  | { nome: "inicial" }
  | { nome: "carregando"; demorando: boolean }
  | { nome: "pronto"; auditoria: Auditoria }
  | { nome: "erro"; erro: ErroDaApi };

export default function Pagina() {
  const [estado, setEstado] = useState<Estado>({ nome: "inicial" });

  async function analisar(arquivo: File, contexto: string) {
    setEstado({ nome: "carregando", demorando: false });
    try {
      const auditoria = await auditar(arquivo, {
        contexto,
        aoDemorar: () =>
          setEstado((atual) =>
            atual.nome === "carregando" ? { nome: "carregando", demorando: true } : atual,
          ),
      });
      setEstado({ nome: "pronto", auditoria });
    } catch (erro) {
      setEstado({
        nome: "erro",
        erro:
          erro instanceof ErroDaApi
            ? erro
            : new ErroDaApi("servidor", "Algo inesperado aconteceu.", "Tente de novo."),
      });
    }
  }

  return (
    <main className="mx-auto max-w-3xl px-6 py-12">
      <header className="mb-10">
        <h1 className="text-2xl font-semibold tracking-tight">Conformidade</h1>
        <p className="mt-2 text-sm text-slate-600">
          Envie sua configuração de Docker ou Kubernetes. Devolvemos o arquivo corrigido,
          pronto para copiar, e explicamos o que estava errado.
        </p>
      </header>

      {estado.nome === "inicial" && <Envio aoEnviar={analisar} ocupado={false} />}
      {estado.nome === "carregando" && <Carregando demorando={estado.demorando} />}
      {estado.nome === "erro" && (
        <Erro erro={estado.erro} aoTentarDeNovo={() => setEstado({ nome: "inicial" })} />
      )}
      {estado.nome === "pronto" && (
        <Resultado
          auditoria={estado.auditoria}
          aoRecomecar={() => setEstado({ nome: "inicial" })}
        />
      )}

      <footer className="mt-16 border-t border-slate-200 pt-6 text-xs text-slate-400">
        A detecção e a correção são determinísticas. A explicação usa IA e passa por um
        verificador que confere cada citação contra a fonte oficial.
      </footer>
    </main>
  );
}
