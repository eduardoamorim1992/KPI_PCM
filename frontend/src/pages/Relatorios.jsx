export default function Relatorios() {
  return (
    <section className="pcm-card space-y-2">
      <h2 className="text-xl font-semibold text-white">Relatórios</h2>
      <p className="text-sm text-slate-400">
        Exportações CSV/Excel/PDF podem ser plugadas aqui consumindo os mesmos endpoints REST (ex.: <span className="font-mono">/api/dashboard/resumo</span>,{" "}
        <span className="font-mono">/api/analitico/overview</span>).
      </p>
    </section>
  );
}
