/**
 * Cliente do progresso em tempo real.
 *
 * `/auditar` só responde quando tudo termina, e a espera é longa: medido,
 * catorze achados levam quase dois minutos. Um indicador de progresso sobre
 * esse endpoint só poderia ser coreografia inventada — bonita, e mentindo
 * sobre o que o sistema faz. Este consome `/auditar/stream`, onde cada camada
 * anuncia início e fim conforme acontece.
 *
 * `fetch` com leitor de stream em vez de `EventSource`: o `EventSource` do
 * navegador só faz GET, e o envio é `multipart` num POST.
 *
 * O desequilíbrio entre as camadas é a razão de o evento de análise reportar
 * achado a achado. As camadas 1, 2 e 4 somam milissegundos; a 3 é ~99% do
 * tempo. Um indicador que trate as quatro como iguais fica parado no terceiro
 * quarto e parece travado — que é justamente a impressão a evitar.
 */

import { ErroDaApi, TIMEOUT_MS } from "@/lib/api";
import type { Auditoria } from "@/lib/contratos";

export type Etapa = "deterministico" | "recuperacao" | "analise" | "critico";

export const ETAPAS: Etapa[] = ["deterministico", "recuperacao", "analise", "critico"];

export const ROTULO_ETAPA: Record<Etapa, { pt: string; en: string }> = {
  deterministico: { pt: "Determinístico", en: "Deterministic" },
  recuperacao: { pt: "Recuperação", en: "Retrieval" },
  analise: { pt: "Análise", en: "Analysis" },
  critico: { pt: "Crítico", en: "Critic" },
};

/** Estado das camadas como a tela precisa desenhar. */
export interface EstadoDoProgresso {
  /** Camada rodando agora, ou `null` antes de começar. */
  atual: Etapa | null;
  concluidas: Set<Etapa>;
  /** Achados já analisados pela camada 3, e o total. */
  analisados: number;
  totalDeAchados: number;
}

export const PROGRESSO_INICIAL: EstadoDoProgresso = {
  atual: null,
  concluidas: new Set(),
  analisados: 0,
  totalDeAchados: 0,
};

type EventoBruto =
  | { tipo: "etapa"; etapa: Etapa; concluida?: boolean; achados?: number; total?: number }
  | { tipo: "analise"; feitos: number; total: number }
  | { tipo: "resultado"; dados: Auditoria }
  | { tipo: "erro"; detalhe: string };

function aplicar(estado: EstadoDoProgresso, evento: EventoBruto): EstadoDoProgresso {
  if (evento.tipo === "etapa") {
    const concluidas = new Set(estado.concluidas);
    if (evento.concluida) concluidas.add(evento.etapa);
    return {
      ...estado,
      concluidas,
      atual: evento.concluida ? estado.atual : evento.etapa,
      totalDeAchados: evento.achados ?? evento.total ?? estado.totalDeAchados,
    };
  }
  if (evento.tipo === "analise") {
    return { ...estado, analisados: evento.feitos, totalDeAchados: evento.total };
  }
  return estado;
}

interface Opcoes {
  contexto?: string;
  aoProgredir?: (estado: EstadoDoProgresso) => void;
  sinal?: AbortSignal;
}

export async function auditarComProgresso(
  arquivo: File,
  { contexto = "", aoProgredir, sinal }: Opcoes = {},
): Promise<Auditoria> {
  const base = (process.env.NEXT_PUBLIC_API_URL ?? "").replace(/\/+$/, "");
  if (!base) {
    throw new ErroDaApi(
      "configuracao",
      "A aplicação não sabe onde encontrar o servidor de análise.",
      "Isto é um erro de configuração do ambiente, não do seu arquivo.",
    );
  }

  const controlador = new AbortController();
  const porTimeout = setTimeout(() => controlador.abort("timeout"), TIMEOUT_MS);
  sinal?.addEventListener("abort", () => controlador.abort("cancelado"), { once: true });

  const corpo = new FormData();
  corpo.append("file", arquivo);
  if (contexto.trim()) corpo.append("contexto", contexto.trim());

  let estado = { ...PROGRESSO_INICIAL, concluidas: new Set<Etapa>() };
  let resultado: Auditoria | null = null;

  try {
    const resposta = await fetch(`${base}/api/v1/auditar/stream`, {
      method: "POST",
      body: corpo,
      signal: controlador.signal,
    });

    if (!resposta.ok || !resposta.body) {
      const { traduzirResposta } = await import("@/lib/api");
      throw await traduzirResposta(resposta);
    }

    const leitor = resposta.body.getReader();
    const decodificador = new TextDecoder();
    let restante = "";

    for (;;) {
      const { done, value } = await leitor.read();
      if (done) break;
      restante += decodificador.decode(value, { stream: true });

      // Um evento SSE termina em linha em branco. Fatiar por `\n` sozinho
      // partiria eventos grandes — o `resultado` carrega o relatório inteiro.
      const blocos = restante.split("\n\n");
      restante = blocos.pop() ?? "";

      for (const bloco of blocos) {
        const linha = bloco.split("\n").find((l) => l.startsWith("data: "));
        if (!linha) continue;
        const evento = JSON.parse(linha.slice(6)) as EventoBruto;

        if (evento.tipo === "erro") {
          throw new ErroDaApi(
            "servidor",
            "O servidor falhou durante a análise.",
            "Tente de novo em alguns instantes.",
            evento.detalhe,
          );
        }
        if (evento.tipo === "resultado") {
          resultado = evento.dados;
          continue;
        }
        estado = aplicar(estado, evento);
        aoProgredir?.(estado);
      }
    }

    if (!resultado) {
      throw new ErroDaApi(
        "servidor",
        "A conexão terminou antes de a análise concluir.",
        "Tente de novo — a segunda tentativa costuma ser rápida por causa do cache.",
      );
    }
    return resultado;
  } catch (erro) {
    if (erro instanceof ErroDaApi) throw erro;
    if (erro instanceof DOMException && erro.name === "AbortError") {
      if (controlador.signal.reason === "cancelado") throw erro;
      throw new ErroDaApi(
        "timeout",
        "A análise passou do tempo limite e foi interrompida.",
        "O servidor pode estar iniciando. Tente de novo — a segunda vez costuma ser rápida.",
      );
    }
    throw new ErroDaApi(
      "rede",
      "Não foi possível falar com o servidor de análise.",
      "Verifique sua conexão. O servidor pode estar fora do ar ou não estar " +
        "autorizando chamadas deste endereço.",
      erro instanceof Error ? erro.message : String(erro),
    );
  } finally {
    clearTimeout(porTimeout);
  }
}
