import { CHART_COLORS } from "../theme/chartTheme";

function corCelula(v) {
  if (v >= 90) return "rgba(16,185,129,0.55)";
  if (v >= 80) return "rgba(245,158,11,0.45)";
  return "rgba(239,68,68,0.45)";
}

export default function HeatmapDM({ linhas, gruposFiltro }) {
  if (!linhas?.length) return <p className="text-sm text-slate-500">Sem dados para heatmap.</p>;
  const grupos = gruposFiltro?.length ? gruposFiltro : [...new Set(linhas.map((r) => r.grupo))].slice(0, 8);
  const semanas = [...new Set(linhas.map((r) => r.semana))].sort().slice(-16);
  const mapa = new Map(linhas.map((r) => [`${r.grupo}|${r.semana}`, r.dm_approx]));

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-xs">
        <thead>
          <tr>
            <th className="border-b border-white/10 p-1 text-left text-slate-400">Grupo</th>
            {semanas.map((s) => (
              <th key={s} className="border-b border-white/10 p-1 text-center font-mono text-[10px] text-slate-500">
                {s.replace("20", "")}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {grupos.map((g) => (
            <tr key={g}>
              <td className="border-b border-white/5 p-1 text-slate-300">{g}</td>
              {semanas.map((s) => {
                const v = mapa.get(`${g}|${s}`);
                return (
                  <td key={s} className="border-b border-white/5 p-0.5 text-center">
                    <div
                      className="mx-auto h-6 w-8 rounded"
                      style={{ background: v != null ? corCelula(v) : CHART_COLORS.muted }}
                      title={v != null ? `${v}%` : "—"}
                    />
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
