/**
 * Estado de espera, ciente do cold start.
 *
 * A API roda com `minReplicas: 0`. Depois de ociosa, a primeira requisição
 * precisa acordar o container e leva de 10 a 20 segundos. Sem aviso, quem está
 * olhando conclui que travou e fecha a página exatamente na primeira vez que
 * usa — a pior hora possível para perder alguém.
 *
 * Por isso a mensagem muda quando a espera se estende: não é só um spinner
 * mais bonito, é a diferença entre "quebrou" e "está acordando".
 */
export function Carregando({ demorando }: { demorando: boolean }) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-lg border border-slate-200 bg-white p-8">
      <div
        className="h-6 w-6 animate-spin rounded-full border-2 border-slate-300 border-t-slate-700"
        role="status"
        aria-label="analisando"
      />
      <p className="text-sm text-slate-700">Analisando sua configuração…</p>
      {demorando && (
        <p className="max-w-md text-center text-xs text-slate-500">
          A primeira análise de um arquivo novo passa por todas as camadas e pode levar
          alguns minutos — o servidor pode estar iniciando, e cada achado é explicado
          individualmente. Analisar o mesmo arquivo de novo é praticamente instantâneo.
        </p>
      )}
    </div>
  );
}
