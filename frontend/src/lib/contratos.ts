/**
 * Espelho do contrato da API — `RespostaAuditoria` em
 * `src/conformidade/api/auditoria.py`.
 *
 * Escrito à mão e não gerado do OpenAPI de propósito, nesta fase: gerar
 * exigiria rodar a API durante o build do frontend, e o ganho seria pequeno
 * para um contrato de dois modelos. O preço é que os dois arquivos podem
 * divergir, e é por isso que cada campo aqui aponta para o nome exato do lado
 * Python — quem mexer num sabe onde procurar o outro.
 *
 * Se o contrato crescer, o caminho é gerar a partir de `/openapi.json`, não
 * manter isto maior.
 */

/** `CitacaoNaResposta` */
export interface Citacao {
  /** Cópia literal do texto oficial, já verificada pela camada 4. */
  trecho: string;
  url: string;
}

/** `AchadoNaResposta` — já achatado pela API para consumo de tela. */
export interface Achado {
  control_id: string;
  titulo: string;
  /** `critical` | `high` | `medium` | `low` | `info` */
  severidade: Severidade;
  /** `confirmado` | `atenuado_por_contexto` | ... */
  veredito: string;
  explicacao: string;
  /** Trecho recortado do arquivo enviado. Renderizar SEMPRE em bloco de código. */
  evidencia: string;
  onde: string;
  citacoes: Citacao[];
  /** Preenchido quando o controle não tem fonte oficial no corpus. */
  aviso_de_respaldo: string;
  /** O que o verificador automático reparou na análise. */
  ressalvas: string[];
  correcao: string;
  correcao_caminho: string;
  corrigido_automaticamente: boolean;
}

/** `RespostaAuditoria` */
export interface Auditoria {
  arquivo: string;
  /** `dockerfile` | `compose` | `kubernetes` */
  formato: Formato;
  total_de_problemas: number;
  corrigidos_automaticamente: string[];
  /** control_id → por que exige decisão humana. */
  dependem_de_voce: Record<string, string>;
  /** `false` quando a camada 3 não participou (Azure indisponível). */
  com_analise: boolean;
  /** O arquivo inteiro, pronto para substituir o original. */
  configuracao_corrigida: string;
  relatorio_markdown: string;
  achados: Achado[];
}

export type Severidade = "critical" | "high" | "medium" | "low" | "info";
export type Formato = "dockerfile" | "compose" | "kubernetes";

/** Ordem de exibição: o que quebra primeiro aparece primeiro. */
export const ORDEM_SEVERIDADE: Severidade[] = [
  "critical",
  "high",
  "medium",
  "low",
  "info",
];

export const ROTULO_SEVERIDADE: Record<Severidade, string> = {
  critical: "crítico",
  high: "alto",
  medium: "médio",
  low: "baixo",
  info: "informativo",
};

/** Linguagem do bloco de código, por formato do arquivo. */
export const LINGUAGEM: Record<Formato, string> = {
  dockerfile: "dockerfile",
  compose: "yaml",
  kubernetes: "yaml",
};

export function agruparPorSeveridade(achados: Achado[]): [Severidade, Achado[]][] {
  return ORDEM_SEVERIDADE.map(
    (s) => [s, achados.filter((a) => a.severidade === s)] as [Severidade, Achado[]],
  ).filter(([, lista]) => lista.length > 0);
}
