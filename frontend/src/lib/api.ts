/**
 * Cliente da API. Único lugar do frontend que sabe que existe rede.
 *
 * ## Duas coisas que o resto do código não deveria precisar saber
 *
 * **Cold start.** O Container App da API roda com `minReplicas: 0` para
 * economizar crédito. Depois de um período ocioso ele desliga, e a primeira
 * requisição precisa acordar o container, o que leva de 10 a 20 segundos. Um
 * timeout de 5s, que pareceria generoso em qualquer outro contexto, faria a
 * aplicação parecer quebrada justamente na primeira vez que alguém a usa.
 *
 * Daí `TIMEOUT_MS` alto e o callback `aoDemorar`: em vez de só esperar, a tela
 * recebe o aviso de que a espera é esperada e explica isso a quem está olhando.
 *
 * **Taxonomia de erro.** O caminho feliz é a parte fácil. O que separa um
 * frontend utilizável de uma tela em branco é cada modo de falha ter uma
 * mensagem própria, em português e sem jargão, porque quem usa isto não sabe
 * o que é status HTTP.
 */

import type { Auditoria } from "@/lib/contratos";

/**
 * Generoso por dois motivos somados, não um.
 *
 * O cold start responde por 10 a 20 segundos. A camada de IA responde pelo
 * resto: o modelo de raciocínio leva ~20s por achado, e um compose comum
 * produz nove. Mesmo com as chamadas paralelizadas, um arquivo grande em
 * servidor frio passa folgado de um minuto.
 *
 * Medido: nove achados em sequência levaram 2m57s; a mesma análise com o
 * cache quente, 0,45s. A primeira vez é sempre a cara.
 */
export const TIMEOUT_MS = 180_000;
/** A partir daqui a tela avisa que a demora é esperada. */
export const AVISO_DEMORA_MS = 4_000;
/** A partir daqui a espera deixou de ser cold start e virou análise. */
export const AVISO_ANALISE_MS = 25_000;

export type TipoDeErro =
  | "configuracao"
  | "arquivo_invalido"
  | "arquivo_grande"
  | "servidor"
  | "timeout"
  | "rede";

export class ErroDaApi extends Error {
  readonly tipo: TipoDeErro;
  /** O que aconteceu, em linguagem de quem não é da área. */
  readonly mensagem: string;
  /** O que a pessoa pode fazer a respeito. Vazio quando não há ação. */
  readonly sugestao: string;
  /** Detalhe técnico, para o rodapé. Nunca é a mensagem principal. */
  readonly detalhe: string;

  constructor(tipo: TipoDeErro, mensagem: string, sugestao = "", detalhe = "") {
    super(mensagem);
    this.name = "ErroDaApi";
    this.tipo = tipo;
    this.mensagem = mensagem;
    this.sugestao = sugestao;
    this.detalhe = detalhe;
  }
}

function baseDaApi(): string {
  const url = process.env.NEXT_PUBLIC_API_URL;
  if (!url) {
    throw new ErroDaApi(
      "configuracao",
      "A aplicação não sabe onde encontrar o servidor de análise.",
      "Isto é um erro de configuração do ambiente, não do seu arquivo. Defina NEXT_PUBLIC_API_URL.",
    );
  }
  return url.replace(/\/+$/, "");
}

async function detalheDoCorpo(resposta: Response): Promise<string> {
  try {
    const corpo = await resposta.json();
    return typeof corpo?.detail === "string" ? corpo.detail : JSON.stringify(corpo?.detail ?? "");
  } catch {
    return "";
  }
}

/** Traduz a resposta de erro. Exportada porque o cliente de stream reusa. */
export async function traduzirResposta(resposta: Response): Promise<ErroDaApi> {
  return traduzir(resposta, await detalheDoCorpo(resposta));
}

function traduzir(resposta: Response, detalhe: string): ErroDaApi {
  if (resposta.status === 413) {
    return new ErroDaApi(
      "arquivo_grande",
      "O arquivo é maior do que o limite aceito.",
      "Envie apenas o arquivo de configuração, não o projeto inteiro.",
      detalhe,
    );
  }
  if (resposta.status === 422) {
    return new ErroDaApi(
      "arquivo_invalido",
      "Não conseguimos interpretar esse arquivo.",
      "Envie um Dockerfile, um docker-compose.yml ou um manifesto do Kubernetes. " +
        "Se o arquivo tiver erro de sintaxe, corrija antes de enviar.",
      detalhe,
    );
  }
  if (resposta.status >= 500) {
    return new ErroDaApi(
      "servidor",
      "O servidor de análise falhou ao processar o arquivo.",
      "Tente de novo em alguns instantes. Se continuar, o problema é nosso, não do seu arquivo.",
      detalhe,
    );
  }
  return new ErroDaApi(
    "servidor",
    "O servidor respondeu de forma inesperada.",
    "Tente de novo em alguns instantes.",
    detalhe || `HTTP ${resposta.status}`,
  );
}

interface Opcoes {
  contexto?: string;
  /** Chamado quando a espera passa de `AVISO_DEMORA_MS`. */
  aoDemorar?: () => void;
  sinal?: AbortSignal;
}

export async function auditar(
  arquivo: File,
  { contexto = "", aoDemorar, sinal }: Opcoes = {},
): Promise<Auditoria> {
  const base = baseDaApi();

  const controlador = new AbortController();
  const porTimeout = setTimeout(() => controlador.abort("timeout"), TIMEOUT_MS);
  const avisoLento = aoDemorar ? setTimeout(aoDemorar, AVISO_DEMORA_MS) : undefined;
  sinal?.addEventListener("abort", () => controlador.abort("cancelado"), { once: true });

  const corpo = new FormData();
  corpo.append("file", arquivo);
  if (contexto.trim()) corpo.append("contexto", contexto.trim());

  try {
    const resposta = await fetch(`${base}/api/v1/auditar`, {
      method: "POST",
      body: corpo,
      signal: controlador.signal,
    });
    if (!resposta.ok) throw traduzir(resposta, await detalheDoCorpo(resposta));
    return (await resposta.json()) as Auditoria;
  } catch (erro) {
    if (erro instanceof ErroDaApi) throw erro;

    if (erro instanceof DOMException && erro.name === "AbortError") {
      if (controlador.signal.reason === "cancelado") throw erro;
      throw new ErroDaApi(
        "timeout",
        "A análise demorou mais do que o esperado e foi interrompida.",
        "O servidor pode estar iniciando. Tente de novo. A segunda tentativa costuma ser rápida.",
      );
    }

    // `fetch` rejeita com TypeError tanto para servidor fora do ar quanto para
    // CORS negado, e o navegador não deixa distinguir os dois por segurança.
    // A mensagem cobre as duas hipóteses em vez de afirmar a errada.
    throw new ErroDaApi(
      "rede",
      "Não foi possível falar com o servidor de análise.",
      "Verifique sua conexão. Se o problema persistir, o servidor pode estar fora do ar " +
        "ou não estar autorizando chamadas deste endereço.",
      erro instanceof Error ? erro.message : String(erro),
    );
  } finally {
    clearTimeout(porTimeout);
    if (avisoLento) clearTimeout(avisoLento);
  }
}

/** Transforma texto colado num `File`, para o mesmo caminho servir aos dois. */
export function arquivoDeTexto(conteudo: string, nome: string): File {
  return new File([conteudo], nome, { type: "text/plain" });
}
