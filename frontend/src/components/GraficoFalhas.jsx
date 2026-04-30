import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { TOOLTIP_STYLE } from "../theme/chartTheme";

const PALETA = ["#00D4FF", "#F59E0B", "#10B981", "#EF4444", "#8B5CF6", "#22C55E", "#64748B", "#F97316", "#6366F1"];

export default function GraficoFalhas({ dados }) {
  return (
    <div className="pcm-card flex h-[360px] flex-col">
      <h3 className="mb-2 text-base font-semibold text-slate-100">Distribuição por tipo de falha</h3>
      <div className="min-h-[280px] flex-1">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie data={dados} dataKey="value" nameKey="name" innerRadius={70} outerRadius={110} paddingAngle={1}>
              {dados.map((_, idx) => (
                <Cell key={idx} fill={PALETA[idx % PALETA.length]} stroke="rgba(0,0,0,0.2)" />
              ))}
            </Pie>
            <Tooltip {...TOOLTIP_STYLE} />
          </PieChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
