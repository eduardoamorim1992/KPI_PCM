import { CHART_COLORS } from "../theme/chartTheme";

function corNivel(nivel) {
  const n = nivel === "CRITICO" ? "CRITICO" : nivel?.replace(/Í/g, "I") ?? "";
  if (n === "CRITICO") return CHART_COLORS.danger;
  if (n === "ALTO") return "#F97316";
  if (n === "MEDIO") return "#F59E0B";
  return CHART_COLORS.success;
}

export default function RankingEquipamentos({ dados }) {
  return (
    <div className="pcm-card">
      <h3 className="mb-3 text-base font-semibold text-slate-100">Top 10 equipamentos críticos</h3>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="text-left text-xs uppercase text-slate-500">
              <th className="border-b border-white/10 pb-2">Código</th>
              <th className="border-b border-white/10 pb-2">Modelo</th>
              <th className="border-b border-white/10 pb-2">Grupo</th>
              <th className="border-b border-white/10 pb-2 font-mono">Índice</th>
              <th className="border-b border-white/10 pb-2">Nível</th>
              <th className="border-b border-white/10 pb-2 font-mono">Hr parado</th>
            </tr>
          </thead>
          <tbody>
            {(dados || []).map((item) => (
              <tr key={item.cod_equipamento} className="border-b border-white/5">
                <td className="py-2 font-mono">{item.cod_equipamento}</td>
                <td className="max-w-[220px] truncate">{item.modelo}</td>
                <td>{item.grupo}</td>
                <td className="font-mono">{item.indice_criticidade}</td>
                <td>
                  <span
                    className="rounded px-2 py-0.5 text-xs font-semibold"
                    style={{ color: corNivel(item.nivel_criticidade), backgroundColor: `${corNivel(item.nivel_criticidade)}22` }}
                  >
                    {item.nivel_criticidade}
                  </span>
                </td>
                <td className="font-mono text-slate-300">{item.horas_parado_total?.toFixed?.(1) ?? item.horas_parado_total}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
