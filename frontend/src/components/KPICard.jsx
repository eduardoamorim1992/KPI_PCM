export default function KPICard({ titulo, valor, subtitulo }) {
  return (
    <article className="pcm-card">
      <p className="mb-1 text-xs font-medium uppercase tracking-wide text-slate-400">{titulo}</p>
      <p className="font-mono text-3xl font-semibold text-white">{valor}</p>
      {subtitulo ? <small className="mt-1 block text-xs text-slate-500">{subtitulo}</small> : null}
    </article>
  );
}
