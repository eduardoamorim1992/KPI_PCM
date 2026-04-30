import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Bar, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { getDashboardOpcoesFiltros, getEquipamentos, getSimulacaoFrota, getUsoAtualEquipamento, postMonteCarlo } from "../api";
import { AXIS_STYLE, CHART_COLORS, TOOLTIP_STYLE } from "../theme/chartTheme";

function corRisco(v) {
  if (v < 30) return CHART_COLORS.success;
  if (v < 60) return CHART_COLORS.secondary;
  return CHART_COLORS.danger;
}

export default function MonteCarlo() {
  const [grupo, setGrupo] = useState("");
  const [codigo, setCodigo] = useState("");
  const [usoAtual, setUsoAtual] = useState(0);
  const [nSim, setNSim] = useState(10000);
  const [grupoFrota, setGrupoFrota] = useState("");

  const opcoes = useQuery({
    queryKey: ["mc-opcoes", grupo],
    queryFn: () => getDashboardOpcoesFiltros({ grupo: grupo || undefined }),
  });
  const equipamentos = useQuery({
    queryKey: ["equipamentos-mc", grupo],
    queryFn: () => getEquipamentos({ grupo: grupo || undefined }),
  });
  const frota = useQuery({
    queryKey: ["sim-frota", grupoFrota],
    queryFn: () => getSimulacaoFrota(grupoFrota || undefined, 8000),
    enabled: false,
  });

  const sim = useMutation({
    mutationFn: () => postMonteCarlo(Number(codigo), { horimetro_atual: usoAtual, n_simulacoes: nSim, horizonte_horas: 2160 }),
  });
  const usoAtualQ = useQuery({
    queryKey: ["uso-atual-equip", codigo],
    enabled: Boolean(codigo),
    queryFn: () => getUsoAtualEquipamento(Number(codigo)),
  });

  const histData = useMemo(() => {
    const h = sim.data?.histograma_residual;
    if (!h) return [];
    return h.map((b) => ({
      name: `${b.x0}-${b.x1}`,
      freq: b.count,
      mid: (b.x0 + b.x1) / 2,
    }));
  }, [sim.data]);

  const cdfData = sim.data?.cdf_residual || [];
  const un = sim.data?.unidade_medida || "HM";
  const horizonsUso = sim.data?.horizontes_uso || [];
  const probsUso = sim.data?.probs_por_horizonte_uso || [];
  const riscoTxt = sim.data
    ? (probsUso[0] ?? sim.data.prob_falha_30d) >= 70
      ? "RISCO ALTO"
      : (probsUso[0] ?? sim.data.prob_falha_30d) >= 40
        ? "RISCO MODERADO"
        : "RISCO BAIXO"
    : null;
  const p50Date = sim.data?.dias_ate_p50 ? new Date(Date.now() + sim.data.dias_ate_p50 * 24 * 3600 * 1000).toLocaleDateString("pt-BR") : null;
  const p90Date = sim.data?.dias_ate_p90 ? new Date(Date.now() + sim.data.dias_ate_p90 * 24 * 3600 * 1000).toLocaleDateString("pt-BR") : null;

  useEffect(() => {
    if (usoAtualQ.data?.uso_atual_sugerido != null && Number.isFinite(usoAtualQ.data.uso_atual_sugerido)) {
      setUsoAtual(Number(usoAtualQ.data.uso_atual_sugerido));
    }
  }, [usoAtualQ.data?.uso_atual_sugerido]);

  return (
    <section className="space-y-4">
      <h2 className="text-xl font-semibold text-white">Simulação Monte Carlo</h2>

      <div className="pcm-card flex flex-col gap-3 md:flex-row md:flex-wrap md:items-end">
        <label className="flex flex-col text-xs text-slate-400">
          Grupo
          <select
            className="pcm-input mt-1 min-w-[200px]"
            value={grupo}
            onChange={(e) => {
              setGrupo(e.target.value);
              setCodigo("");
            }}
          >
            <option value="">Todos os grupos</option>
            {(opcoes.data?.grupos || []).map((g) => (
              <option key={g} value={g}>
                {g}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col text-xs text-slate-400">
          Frota (equipamento)
          <select className="pcm-input mt-1 min-w-[220px]" value={codigo} onChange={(e) => setCodigo(e.target.value)}>
            <option value="">Selecione...</option>
            {(equipamentos.data || []).slice(0, 1200).map((e) => (
              <option key={e.cod_equipamento} value={e.cod_equipamento}>
                {e.cod_equipamento} - {e.modelo}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col text-xs text-slate-400">
          Uso atual (h/km desde última falha)
          <input className="pcm-input mt-1 w-40" type="number" value={usoAtual} onChange={(e) => setUsoAtual(Number(e.target.value))} />
          {usoAtualQ.data && <small className="mt-1 text-[10px] text-slate-500">Sugerido: {usoAtualQ.data.uso_atual_sugerido} {usoAtualQ.data.unidade_medida}</small>}
        </label>
        <label className="flex flex-1 flex-col text-xs text-slate-400">
          Simulações: {nSim.toLocaleString("pt-BR")}
          <input
            className="mt-2 w-full accent-pcm-cyan"
            type="range"
            min={1000}
            max={50000}
            step={1000}
            value={nSim}
            onChange={(e) => setNSim(Number(e.target.value))}
          />
        </label>
        <button type="button" className="pcm-btn px-6" disabled={!codigo || sim.isPending} onClick={() => sim.mutate()}>
          {sim.isPending ? "Executando..." : "▶ Executar simulação"}
        </button>
      </div>

      {sim.isError && <p className="text-sm text-red-300">{String(sim.error?.message || sim.error)}</p>}

      {sim.data && (
        <>
          <div className="pcm-card border-cyan-500/25">
            <p className="text-sm text-slate-300">
              Diagnóstico: <span className="font-semibold text-white">{riscoTxt}</span> • Observações históricas:{" "}
              <span className="font-mono">{sim.data.n_observacoes}</span> • Ajuste KS p-value:{" "}
              <span className="font-mono">{Number(sim.data.ks_pvalue || 0).toFixed(3)}</span>
            </p>
            {sim.data.aviso_simulacao && <p className="mt-2 text-xs text-amber-200">{sim.data.aviso_simulacao}</p>}
          </div>
          <div className="grid gap-3 md:grid-cols-3">
            <div className="pcm-card">
              <p className="text-xs uppercase tracking-wide text-slate-400">Mediana • P50</p>
              <p className="font-mono text-2xl text-white">{sim.data.p50} {un} até falha residual</p>
              <small className="text-slate-500">{p50Date ? `Data estimada: ${p50Date}` : "Estimativa por uso do ativo."}</small>
            </div>
            <div className="pcm-card border-amber-500/25">
              <p className="text-xs uppercase tracking-wide text-amber-300">Limite alto • P90</p>
              <p className="font-mono text-2xl text-white">{sim.data.p90} {un}</p>
              <small className="text-slate-500">{p90Date ? `Janela conservadora até ${p90Date}` : "Cenário conservador por uso acumulado."}</small>
            </div>
            <div className="pcm-card border-emerald-500/25">
              <p className="text-xs uppercase tracking-wide text-emerald-300">Preventiva recomendada</p>
              <p className="font-mono text-2xl text-white">{sim.data.intervalo_preventiva_otimo} {un}</p>
              <small className="text-slate-500">{sim.data.weibull_interpretacao}</small>
            </div>
          </div>

          <div className="pcm-card">
            <p className="mb-2 text-sm font-semibold text-slate-100">Recomendação prática</p>
            <ul className="space-y-1 text-sm text-slate-300">
              <li>• Agendar preventiva até <span className="font-mono text-white">{sim.data.intervalo_preventiva_otimo} {un}</span> de uso acumulado.</li>
              <li>• Se meta for risco baixo, atuar antes de <span className="font-mono text-white">P50 ({sim.data.p50} {un})</span>.</li>
              <li>• Para janela segura, planejar peças para até <span className="font-mono text-white">P90 ({sim.data.p90} {un})</span>.</li>
            </ul>
            {sim.data.alertas?.length > 0 && (
              <div className="mt-3 space-y-2">
                {sim.data.alertas.map((a) => (
                  <div key={a.id} className="rounded border border-amber-500/30 bg-amber-500/10 p-2 text-xs text-amber-100">
                    <strong>{a.nivel}</strong>: {a.mensagem} — <span className="font-semibold">{a.acao}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="grid gap-3 md:grid-cols-2">
            <div className="pcm-card h-[300px]">
              <h3 className="mb-2 text-sm font-semibold text-slate-100">Histograma — tempo residual simulado</h3>
              <ResponsiveContainer>
                <ComposedChart data={histData}>
                  <CartesianGrid stroke={CHART_COLORS.grid} />
                  <XAxis dataKey="mid" {...AXIS_STYLE} />
                  <YAxis {...AXIS_STYLE} />
                  <Tooltip {...TOOLTIP_STYLE} />
                  <Bar dataKey="freq" fill={`${CHART_COLORS.primary}88`} name=" Frequência" radius={[6, 6, 0, 0]} />
                  <ReferenceLine x={sim.data.p50} stroke={CHART_COLORS.secondary} strokeDasharray="4 3" />
                  <ReferenceLine x={sim.data.p90} stroke={CHART_COLORS.danger} strokeDasharray="4 3" />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
            <div className="pcm-card h-[300px]">
              <h3 className="mb-2 text-sm font-semibold text-slate-100">CDF empírica (simulações)</h3>
              <ResponsiveContainer>
                <ComposedChart data={cdfData}>
                  <CartesianGrid stroke={CHART_COLORS.grid} />
                  <XAxis dataKey="t" type="number" {...AXIS_STYLE} />
                  <YAxis {...AXIS_STYLE} domain={[0, 1]} />
                  <Tooltip {...TOOLTIP_STYLE} />
                  <Line type="monotone" dataKey="F" stroke={CHART_COLORS.primary} dot={false} strokeWidth={2} />
                  <ReferenceLine x={sim.data.p50} stroke={CHART_COLORS.secondary} strokeDasharray="4 3" />
                  <ReferenceLine x={sim.data.p90} stroke={CHART_COLORS.danger} strokeDasharray="4 3" />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="pcm-card space-y-2">
            <p className="text-sm font-semibold text-slate-100">Probabilidades por horizonte de deslocamento/uso ({un})</p>
            {horizonsUso.map((h, idx) => {
              const val = probsUso[idx] ?? 0;
              return (
              <div key={`${h}-${un}`} className="flex items-center gap-3 text-sm text-slate-300">
                <span className="w-40">Próximos {h} {un}</span>
                <div className="h-2 flex-1 overflow-hidden rounded-full bg-slate-800">
                  <div className="h-full rounded-full bg-gradient-to-r from-pcm-cyan to-amber-400" style={{ width: `${Math.min(val, 100)}%` }} />
                </div>
                <span className="w-12 text-right font-mono text-white">{val}%</span>
              </div>
              );
            })}
          </div>
        </>
      )}

      <div className="pcm-card space-y-3">
        <div className="flex flex-wrap items-end gap-3">
          <label className="text-xs text-slate-400">
            Filtrar frota por grupo
            <input
              className="pcm-input mt-1"
              placeholder="Ex.: COLHEDORAS"
              value={grupoFrota}
              onChange={(e) => setGrupoFrota(e.target.value.toUpperCase())}
            />
          </label>
          <button type="button" className="pcm-btn" onClick={() => frota.refetch()}>
            Carregar ranking de risco
          </button>
        </div>
        {frota.isFetching && <p className="text-sm text-slate-500">Simulando frota (pode levar alguns segundos)…</p>}
        {frota.data && (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-sm">
              <thead>
                <tr className="border-b border-white/10 text-left text-xs uppercase text-slate-500">
                  <th className="py-2">Equipamento</th>
                  <th>Grupo</th>
                  <th className="text-right">P90 uso</th>
                  <th className="text-right">Curto uso</th>
                </tr>
              </thead>
              <tbody>
                {frota.data.slice(0, 40).map((row) => (
                  <tr key={row.cod_equipamento} className="border-b border-white/5">
                    <td className="py-2 font-mono text-white">{row.cod_equipamento}</td>
                    <td>{row.grupo}</td>
                    <td className="text-right font-mono" style={{ color: corRisco(row.prob_falha_90d) }}>
                      {row.prob_falha_90d?.toFixed?.(1) ?? row.prob_falha_90d}%
                    </td>
                    <td className="text-right font-mono text-slate-300">{row.prob_falha_30d?.toFixed?.(1) ?? row.prob_falha_30d}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {frota.error && <p className="text-xs text-amber-200">Não foi possível simular a frota completa (muitos equipamentos sem histórico suficiente).</p>}
      </div>
    </section>
  );
}
