import { LayoutGrid } from "lucide-react";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useEffect, useMemo, useState } from "react";
import FilterBar from "../components/FilterBar";
import GraficoFalhas from "../components/GraficoFalhas";
import KPICard from "../components/KPICard";
import RankingEquipamentos from "../components/RankingEquipamentos";
import { useRanking, useResumo } from "../hooks/useKPIs";
import { useFilterStore } from "../store/filterStore";
import { AXIS_STYLE, CHART_COLORS, TOOLTIP_STYLE } from "../theme/chartTheme";
import { useQuery } from "@tanstack/react-query";
import { getDashboardOpcoesFiltros } from "../api";

export default function Dashboard() {
  const { grupo, frota, modelo, setGrupo, setFrota, setModelo } = useFilterStore();
  const [dtInicio, setDtInicio] = useState("");
  const [dtFim, setDtFim] = useState("");
  const [tipoFalha, setTipoFalha] = useState("");

  const opcoesQ = useQuery({
    queryKey: ["dashboard-opcoes", grupo, frota],
    queryFn: () => getDashboardOpcoesFiltros({ grupo, frota: frota ? Number(frota) : undefined }),
    staleTime: 10 * 60 * 1000,
  });

  const params = useMemo(
    () => ({
      ...(grupo ? { grupo } : {}),
      ...(frota ? { frota: Number(frota) } : {}),
      ...(modelo ? { modelo } : {}),
      ...(dtInicio ? { dt_inicio: dtInicio } : {}),
      ...(dtFim ? { dt_fim: dtFim } : {}),
      ...(tipoFalha ? { tipo_falha: tipoFalha } : {}),
    }),
    [grupo, frota, modelo, dtInicio, dtFim, tipoFalha],
  );
  const resumo = useResumo(params);
  const ranking = useRanking(10, grupo || undefined);

  useEffect(() => {
    const frotas = opcoesQ.data?.frotas || [];
    if (frota && !frotas.some((f) => String(f.cod_equipamento) === String(frota))) {
      setFrota("");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [opcoesQ.data?.frotas, frota]);

  useEffect(() => {
    const modelos = opcoesQ.data?.modelos || [];
    if (modelo && !modelos.includes(modelo)) {
      setModelo("");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [opcoesQ.data?.modelos, modelo]);

  if (resumo.isLoading)
    return (
      <div className="pcm-card flex items-center justify-between gap-3">
        <span>Carregando painel executivo…</span>
        <button type="button" className="pcm-btn" onClick={() => resumo.refetch()}>
          Tentar novamente
        </button>
      </div>
    );
  if (resumo.error) {
    return (
      <div className="pcm-card border-red-500/30 text-red-200">
        Falha ao carregar o dashboard. Verifique se o backend está em <span className="font-mono">http://localhost:8000</span>.
      </div>
    );
  }

  const data = resumo.data;
  const falhas = Object.entries(data.falhas_por_tipo || {}).map(([name, value]) => ({ name, value }));
  const falhasMensal = data.os_mensal_por_falha?.series || [];
  const tiposSeries = data.os_mensal_por_falha?.tipos || [];

  const tiposFalhaOpcoes = opcoesQ.data?.tipos_falha || Object.keys(data.falhas_por_tipo || {});

  return (
    <section className="space-y-4">
      <div className="flex items-center gap-2">
        <LayoutGrid className="h-6 w-6 text-pcm-cyan" />
        <h2 className="text-xl font-semibold text-white">Dashboard executivo</h2>
      </div>

      <FilterBar>
        <select
          className="pcm-input min-w-[220px]"
          value={grupo}
          onChange={(e) => {
            setGrupo(e.target.value.toUpperCase());
            setFrota("");
            setModelo("");
          }}
        >
          <option value="">Todos os tipos (grupo)</option>
          {(opcoesQ.data?.grupos || []).map((g) => (
            <option key={g} value={g}>
              {g}
            </option>
          ))}
        </select>

        <select
          className="pcm-input min-w-[200px]"
          value={frota}
          onChange={(e) => setFrota(e.target.value)}
          disabled={!grupo}
        >
          <option value="">{grupo ? "Todas as frotas" : "Selecione grupo primeiro"}</option>
          {(opcoesQ.data?.frotas || []).map((f) => (
            <option key={f.cod_equipamento} value={f.cod_equipamento}>
              {f.cod_equipamento} - {f.modelo}
            </option>
          ))}
        </select>

        <select
          className="pcm-input min-w-[240px]"
          value={modelo}
          onChange={(e) => setModelo(e.target.value.toUpperCase())}
          disabled={!grupo}
        >
          <option value="">{grupo ? "Todos os modelos" : "Selecione grupo primeiro"}</option>
          {(opcoesQ.data?.modelos || []).map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </select>

        <input className="pcm-input w-[160px]" type="date" value={dtInicio} onChange={(e) => setDtInicio(e.target.value)} />
        <input className="pcm-input w-[160px]" type="date" value={dtFim} onChange={(e) => setDtFim(e.target.value)} />
        <select className="pcm-input min-w-[240px]" value={tipoFalha} onChange={(e) => setTipoFalha(e.target.value)}>
          <option value="">Todas as falhas</option>
          {tiposFalhaOpcoes.slice(0, 30).map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
        <button type="button" className="pcm-btn" onClick={() => resumo.refetch()}>
          Atualizar
        </button>
      </FilterBar>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
        <KPICard titulo="Total de OS no período" valor={data.totais.total_os?.toLocaleString?.("pt-BR") ?? "—"} subtitulo="Histórico filtrado" />
        <KPICard titulo="MTTR médio (frota)" valor={`${data.kpis.mttr_medio_horas} h`} subtitulo="Todas as OS (referência rápida)" />
        <KPICard titulo="Disponibilidade média (%)" valor={`${(data.kpis.dm_frota_media_pct ?? 0).toFixed(1)}%`} subtitulo="Média simples das DM por grupo" />
        <KPICard
          titulo="OS vs mês anterior"
          valor={data.kpis.variacao_os_mom_pct != null ? `${data.kpis.variacao_os_mom_pct > 0 ? "+" : ""}${data.kpis.variacao_os_mom_pct}%` : "—"}
          subtitulo="Último mês completo do filtro"
        />
      </div>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
        <KPICard titulo="% corretivas" valor={`${data.kpis.pct_corretiva}%`} subtitulo="Participação sobre total de OS" />
        <KPICard titulo="O.S encerradas no período" valor={data.kpis.os_encerradas_periodo ?? 0} subtitulo="Status encerrada (E)" />
        <KPICard titulo="O.S abertas no período" valor={data.kpis.os_abertas_periodo ?? 0} subtitulo="Status diferente de encerrada (E)" />
        <KPICard titulo="Ativos cobertos" valor={data.totais.total_equipamentos} subtitulo="Códigos distintos com OS registradas" />
      </div>

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-3">
        <div className="pcm-card xl:col-span-2">
          <h3 className="mb-2 text-base font-semibold text-slate-100">Falhas reais por mês (coluna I — DE_MOTENTR)</h3>
          <div className="h-[320px] w-full">
            <ResponsiveContainer>
              <AreaChart data={falhasMensal}>
                <defs>
                  <linearGradient id="gc" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor={CHART_COLORS.primary} stopOpacity={0.8} />
                    <stop offset="95%" stopColor={CHART_COLORS.primary} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke={CHART_COLORS.grid} />
                <XAxis dataKey="mes" {...AXIS_STYLE} />
                <YAxis {...AXIS_STYLE} />
                <Tooltip {...TOOLTIP_STYLE} />
                {tiposSeries.map((t, idx) => (
                  <Area
                    key={t}
                    type="monotone"
                    dataKey={t}
                    stackId="1"
                    stroke={idx % 2 === 0 ? CHART_COLORS.primary : CHART_COLORS.secondary}
                    fill={idx === 0 ? "url(#gc)" : `${idx % 2 === 0 ? CHART_COLORS.primary : CHART_COLORS.secondary}33`}
                  />
                ))}
                <Area type="monotone" dataKey="OUTRAS" stackId="1" stroke={CHART_COLORS.muted} fill={`${CHART_COLORS.muted}22`} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
        <GraficoFalhas dados={falhas} />
      </div>

      <RankingEquipamentos dados={ranking.data || []} />
    </section>
  );
}
