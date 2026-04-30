import { useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  Cell,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  Line,
  LineChart,
  Legend,
  ComposedChart,
} from "recharts";
import GaugeDM from "../components/GaugeDM";
import HeatmapDM from "../components/HeatmapDM";
import { useQuery } from "@tanstack/react-query";
import { getDashboardOpcoesFiltros } from "../api";
import { useAnalitico } from "../hooks/useAnalitico";
import { useResumo } from "../hooks/useKPIs";
import { CHART_COLORS, TOOLTIP_STYLE, AXIS_STYLE } from "../theme/chartTheme";
import FilterBar from "../components/FilterBar";

export default function Analitico() {
  const [grupo, setGrupo] = useState("");
  const [frota, setFrota] = useState("");
  const params = useMemo(() => ({ ...(grupo ? { grupo } : {}), ...(frota ? { frota: Number(frota) } : {}) }), [grupo, frota]);
  const opcoesQ = useQuery({
    queryKey: ["analitico-opcoes", grupo, frota],
    queryFn: () => getDashboardOpcoesFiltros({ grupo: grupo || undefined, frota: frota ? Number(frota) : undefined }),
  });
  const resumo = useResumo(params);
  const q = useAnalitico(params);
  const [grupoDm, setGrupoDm] = useState("");

  if (q.isLoading) return <div className="pcm-card">Carregando painel analítico…</div>;
  if (q.error) return <div className="pcm-card border-red-500/30 text-red-100">Erro ao carregar /api/analitico/overview</div>;

  const d = q.data;
  const mtPairs = (d.mtbf_mttr_por_grupo || []).map((row) => ({
    ...row,
    label: row.grupo,
  }));

  const topF = d.top_falhas_equip || [];
  const falStack = d.falhas_stack_mes || { meses_linhas: [], tipos: [] };
  const comp = d.composicao_origem || [];
  const evoMttr = d.evolucao_mttr_mensal || [];
  const criticidadeABC = d.criticidade_abc || [];
  const backlog = d.backlog_aging || { kpis: {}, faixas: [] };

  const gruposDistinct = [...new Set((d.heatmap_dm || []).map((r) => r.grupo))].slice(0, 8);

  return (
    <section className="space-y-4">
      <h2 className="text-xl font-semibold text-white">Indicadores analíticos</h2>

      <FilterBar>
        <select
          className="pcm-input min-w-[220px]"
          value={grupo}
          onChange={(e) => {
            setGrupo(e.target.value);
            setFrota("");
            setGrupoDm("");
          }}
        >
          <option value="">Todos os grupos</option>
          {(opcoesQ.data?.grupos || []).map((g) => (
            <option key={g} value={g}>
              {g}
            </option>
          ))}
        </select>
        <select className="pcm-input min-w-[220px]" value={frota} onChange={(e) => setFrota(e.target.value)} disabled={!grupo}>
          <option value="">{grupo ? "Todas as frotas" : "Selecione grupo"}</option>
          {(opcoesQ.data?.frotas || []).map((f) => (
            <option key={f.cod_equipamento} value={f.cod_equipamento}>
              {f.cod_equipamento} - {f.modelo}
            </option>
          ))}
        </select>
      </FilterBar>

      <div className="grid gap-3 lg:grid-cols-[2fr,1fr]">
        <div className="pcm-card h-[380px]">
          <h3 className="mb-2 text-base font-semibold text-slate-100">MTBF vs MTTR por grupo</h3>
          <ResponsiveContainer>
            <BarChart layout="vertical" data={mtPairs} margin={{ left: 110 }}>
              <CartesianGrid stroke={CHART_COLORS.grid} horizontal={false} />
              <XAxis type="number" {...AXIS_STYLE} />
              <YAxis type="category" dataKey="grupo" {...AXIS_STYLE} width={105} />
              <Tooltip {...TOOLTIP_STYLE} />
              <Bar dataKey="mtbf_medio" fill={CHART_COLORS.primary} name="MTBF médio (h equip.)" radius={[0, 4, 4, 0]} />
              <Bar dataKey="mttr_medio" fill={CHART_COLORS.secondary} name="MTTR médio (falhas reais)" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="pcm-card">
          <h3 className="mb-2 text-base font-semibold text-slate-100">Gauge de DM vs meta</h3>
          <div className="space-y-2">
            <select className="pcm-input w-full" value={grupoDm} onChange={(e) => setGrupoDm(e.target.value)}>
              <option value="">Selecionar grupo...</option>
              {mtPairs.map((g) => (
                <option key={g.grupo} value={g.grupo}>
                  {g.grupo}
                </option>
              ))}
            </select>
            <GaugeDM
              valor={(() => {
                const rows = resumo.data?.disponibilidade_por_grupo || [];
                if (grupoDm) return rows.find((r) => r.grupo === grupoDm)?.disponibilidade_pct ?? 0;
                return resumo.data?.kpis?.dm_frota_media_pct ?? 0;
              })()}
              meta={88}
              label={grupoDm || "DM consolidada"}
            />
            <small className="block text-[11px] text-slate-500">Fonte: /api/dashboard/resumo (mesmo filtro).</small>
          </div>
        </div>
      </div>

      <div className="pcm-card h-[340px]">
        <h3 className="mb-2 text-base font-semibold text-slate-100">Tendência de MTTR (falhas reais)</h3>
        <ResponsiveContainer>
          <LineChart data={evoMttr}>
            <CartesianGrid stroke={CHART_COLORS.grid} />
            <XAxis dataKey="mes" {...AXIS_STYLE} />
            <YAxis {...AXIS_STYLE} />
            <Tooltip {...TOOLTIP_STYLE} />
            <Legend />
            <Line type="monotone" dataKey="mttr_medio" stroke={CHART_COLORS.secondary} strokeWidth={2} dot={false} name="MTTR médio (h)" />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div className="pcm-card h-[360px]">
        <h3 className="mb-2 text-base font-semibold text-slate-100">Falhas por tipo ao longo do tempo</h3>
        <ResponsiveContainer>
          <ComposedChart data={falStack.meses_linhas || []}>
            <CartesianGrid stroke={CHART_COLORS.grid} />
            <XAxis dataKey="mes" {...AXIS_STYLE} />
            <YAxis {...AXIS_STYLE} />
            <Tooltip {...TOOLTIP_STYLE} />
            <Legend />
            {(falStack.tipos || []).slice(0, 5).map((tipo, idx) => (
              <Bar key={tipo} stackId="a" dataKey={tipo} fill={idx % 2 ? CHART_COLORS.primary : CHART_COLORS.danger} name={tipo} />
            ))}
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        <div className="pcm-card h-[360px]">
          <h3 className="mb-2 text-base font-semibold text-slate-100">Composição (% origens) por grupo</h3>
          <ResponsiveContainer>
            <BarChart data={comp}>
              <CartesianGrid stroke={CHART_COLORS.grid} />
              <XAxis dataKey="grupo" {...AXIS_STYLE} interval={0} angle={-20} height={85} dy={24} dx={4} />
              <YAxis {...AXIS_STYLE} />
              <Tooltip {...TOOLTIP_STYLE} />
              <Legend />
              <Bar dataKey="pct_corretiva" stackId="a" fill={CHART_COLORS.corretiva} name="% Corretivas" />
              <Bar dataKey="pct_programada" stackId="a" fill={CHART_COLORS.programada} name="% Programadas" />
              <Bar dataKey="pct_terceirizada" stackId="a" fill={CHART_COLORS.terceirizada} name="% Terceirizadas" />
              <Bar dataKey="pct_outros" stackId="a" fill={CHART_COLORS.outros} name="% Demais" />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="pcm-card h-[340px]">
          <h3 className="mb-2 text-base font-semibold text-slate-100">Top frotas por nº falhas</h3>
          <ResponsiveContainer>
            <BarChart layout="vertical" data={[...topF].reverse()} margin={{ left: 120 }}>
              <CartesianGrid stroke={CHART_COLORS.grid} />
              <XAxis type="number" {...AXIS_STYLE} />
              <YAxis type="category" dataKey="frota" width={105} {...AXIS_STYLE} />
              <Tooltip {...TOOLTIP_STYLE} />
              <Bar dataKey="n_falhas" fill={CHART_COLORS.secondary} radius={[0, 4, 4, 0]} name="Qtd falhas reais" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="pcm-card">
        <h3 className="mb-2 text-base font-semibold text-slate-100">Heatmap semanal (DM aprox.)</h3>
        <HeatmapDM linhas={d.heatmap_dm} gruposFiltro={gruposDistinct.length ? gruposDistinct : undefined} />
      </div>

      <div className="grid gap-3 lg:grid-cols-[1.4fr,1fr]">
        <div className="pcm-card h-[360px]">
          <h3 className="mb-2 text-base font-semibold text-slate-100">Backlog técnico por aging (O.S abertas)</h3>
          <div className="mb-2 grid grid-cols-2 gap-2 text-xs text-slate-300 md:grid-cols-4">
            <div className="rounded border border-white/10 p-2">Abertas: <span className="font-mono text-white">{backlog.kpis?.total_abertas ?? 0}</span></div>
            <div className="rounded border border-white/10 p-2">Idade média: <span className="font-mono text-white">{backlog.kpis?.idade_media_dias ?? 0} d</span></div>
            <div className="rounded border border-white/10 p-2">P90 idade: <span className="font-mono text-white">{backlog.kpis?.idade_p90_dias ?? 0} d</span></div>
            <div className="rounded border border-white/10 p-2">% &gt; 30d: <span className="font-mono text-white">{backlog.kpis?.pct_maior_30d ?? 0}%</span></div>
          </div>
          <ResponsiveContainer>
            <BarChart data={backlog.faixas || []}>
              <CartesianGrid stroke={CHART_COLORS.grid} />
              <XAxis dataKey="faixa" {...AXIS_STYLE} />
              <YAxis {...AXIS_STYLE} />
              <Tooltip {...TOOLTIP_STYLE} />
              <Bar dataKey="qtd_os" name="Qtd O.S abertas">
                {(backlog.faixas || []).map((r) => (
                  <Cell
                    key={r.faixa}
                    fill={r.faixa === ">60" ? CHART_COLORS.danger : r.faixa === "31-60" ? CHART_COLORS.secondary : CHART_COLORS.primary}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="pcm-card">
          <h3 className="mb-2 text-base font-semibold text-slate-100">Matriz ABC de criticidade (impacto x frequência x MTTR)</h3>
          <div className="max-h-[300px] overflow-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-white/10 text-left uppercase text-slate-500">
                  <th className="py-2">Frota</th>
                  <th className="text-right">Score</th>
                  <th className="text-right">Falhas</th>
                  <th className="text-right">MTTR</th>
                  <th className="text-right">ABC</th>
                </tr>
              </thead>
              <tbody>
                {criticidadeABC.slice(0, 15).map((row) => (
                  <tr key={row.cod_equipamento} className="border-b border-white/5 text-slate-300">
                    <td className="py-2 font-mono text-white">{row.frota}</td>
                    <td className="text-right font-mono">{row.score_criticidade}</td>
                    <td className="text-right">{row.falhas_reais}</td>
                    <td className="text-right">{row.mttr_horas}h</td>
                    <td
                      className="text-right font-semibold"
                      style={{
                        color:
                          row.classe_abc === "A"
                            ? CHART_COLORS.danger
                            : row.classe_abc === "B"
                              ? CHART_COLORS.secondary
                              : CHART_COLORS.primary,
                      }}
                    >
                      {row.classe_abc}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </section>
  );
}
