import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  CartesianGrid,
  ComposedChart,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { getConfiabilidadeEquipamento, getDashboardOpcoesFiltros, getGrupoAnalise, getGrupos } from "../api";
import { AXIS_STYLE, CHART_COLORS, TOOLTIP_STYLE } from "../theme/chartTheme";
import FilterBar from "../components/FilterBar";

export default function Confiabilidade() {
  const [modo, setModo] = useState("equipamento"); // equipamento | grupo
  const [codigo, setCodigo] = useState("");
  const [grupoEq, setGrupoEq] = useState("");
  const [frotaEq, setFrotaEq] = useState("");
  const [modeloEq, setModeloEq] = useState("");
  const [grupo, setGrupo] = useState("");

  const gruposQ = useQuery({ queryKey: ["grupos"], queryFn: getGrupos });
  const opcoesEq = useQuery({
    queryKey: ["confi-opcoes-eq", grupoEq, frotaEq],
    queryFn: () => getDashboardOpcoesFiltros({ grupo: grupoEq || undefined, frota: frotaEq ? Number(frotaEq) : undefined }),
  });

  const qEq = useQuery({
    queryKey: ["confi-equipamento", codigo],
    enabled: modo === "equipamento" && Boolean(codigo),
    queryFn: () => getConfiabilidadeEquipamento(Number(codigo)),
  });

  const qGr = useQuery({
    queryKey: ["confi-grupo", grupo],
    enabled: modo === "grupo" && Boolean(grupo),
    queryFn: () => getGrupoAnalise(grupo),
  });

  const [aba, setAba] = useState("rt"); // rt | ht | papel

  const curvaRt = modo === "equipamento" && qEq.data?.curva;
  const curvaGrupo = modo === "grupo" && qGr.data?.curva_banheira?.curva;

  const ptsR = useMemo(() => {
    const c = curvaRt || curvaGrupo;
    if (!c?.t) return [];
    return c.t.map((t, i) => ({ t: t, R: (c.R_t || [])[i] }));
  }, [curvaRt, curvaGrupo]);

  const ptsH = useMemo(() => {
    const c = curvaRt || curvaGrupo;
    if (!c?.t) return [];
    return c.t.map((t, i) => ({ t: t, h: (c.h_t || [])[i] }));
  }, [curvaRt, curvaGrupo]);
  const ptsRH = useMemo(() => {
    const n = Math.min(ptsR.length, ptsH.length);
    const out = [];
    for (let i = 0; i < n; i += 1) out.push({ t: ptsR[i].t, R: ptsR[i].R, h: ptsH[i].h });
    return out;
  }, [ptsR, ptsH]);

  const papelObs = modo === "equipamento" && qEq.data?.papel_weibull?.observados;
  const papelAjust = modo === "equipamento" && qEq.data?.papel_weibull?.ajuste;

  const params = modo === "equipamento" && qEq.data?.parametros;

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-xl font-semibold text-white">Confiabilidade Weibull</h2>
        <div className="flex rounded-lg border border-white/10 p-1 text-xs">
          <button
            type="button"
            className={`rounded-md px-3 py-1 ${modo === "equipamento" ? "bg-pcm-cyan/20 text-pcm-cyan" : "text-slate-400"}`}
            onClick={() => setModo("equipamento")}
          >
            Equipamento
          </button>
          <button
            type="button"
            className={`rounded-md px-3 py-1 ${modo === "grupo" ? "bg-pcm-cyan/20 text-pcm-cyan" : "text-slate-400"}`}
            onClick={() => setModo("grupo")}
          >
            Grupo
          </button>
        </div>
      </div>

      {modo === "equipamento" && (
        <FilterBar>
          <select
            className="pcm-input min-w-[220px]"
            value={grupoEq}
            onChange={(e) => {
              setGrupoEq(e.target.value);
              setFrotaEq("");
              setModeloEq("");
              setCodigo("");
            }}
          >
            <option value="">Tipo de equipamento (todos)</option>
            {(opcoesEq.data?.grupos || []).map((g) => (
              <option key={g} value={g}>
                {g}
              </option>
            ))}
          </select>

          <select
            className="pcm-input min-w-[240px]"
            value={frotaEq}
            disabled={!grupoEq}
            onChange={(e) => {
              const v = e.target.value;
              setFrotaEq(v);
              setCodigo(v);
            }}
          >
            <option value="">{grupoEq ? "Frota (equipamento)" : "Selecione grupo primeiro"}</option>
            {(opcoesEq.data?.frotas || [])
              .filter((f) => !modeloEq || f.modelo === modeloEq)
              .map((f) => (
                <option key={f.cod_equipamento} value={f.cod_equipamento}>
                  {f.cod_equipamento} - {f.modelo}
                </option>
              ))}
          </select>

          <select
            className="pcm-input min-w-[260px]"
            value={modeloEq}
            disabled={!grupoEq}
            onChange={(e) => {
              setModeloEq(e.target.value);
              setFrotaEq("");
              setCodigo("");
            }}
          >
            <option value="">{grupoEq ? "Modelo do equipamento (todos)" : "Selecione grupo primeiro"}</option>
            {(opcoesEq.data?.modelos || []).map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </FilterBar>
      )}

      {modo === "grupo" && (
        <FilterBar>
          <select className="pcm-input min-w-[240px]" value={grupo} onChange={(e) => setGrupo(e.target.value)}>
            <option value="">Selecione</option>
            {(gruposQ.data || []).map((g) => (
              <option key={g.grupo_equipamento} value={g.grupo_equipamento}>
                {g.grupo_equipamento}
              </option>
            ))}
          </select>
        </FilterBar>
      )}

      {(qEq.isFetching || qGr.isFetching) && <p className="text-sm text-slate-400">Carregando curvas...</p>}
      {(qEq.error || qGr.error) && <p className="text-sm text-red-300">Não há histórico suficiente ou agrupamento não encontrado.</p>}

      {params && modo === "equipamento" && (
        <div className="pcm-card flex flex-wrap gap-4 text-sm text-slate-200">
          <span className="font-mono">
            β = {params.beta?.toFixed?.(3) ?? params.beta}
          </span>
          <span className="font-mono">
            η = {params.eta?.toFixed?.(1) ?? params.eta}{" "}
            <small className="text-slate-500">(uso da métrica ajustada)</small>
          </span>
          <span className="font-mono">R² = {params.r_quadrado ?? "—"}</span>
        </div>
      )}

      {modo === "grupo" && qGr.data?.curva_banheira && (
        <div className="pcm-card flex flex-wrap items-center gap-3 text-xs text-slate-300">
          <span className="font-mono text-sm text-white">β̃ = {qGr.data.curva_banheira.beta_medio}</span>
          <span className="font-mono text-sm text-white">η̃ = {qGr.data.curva_banheira.eta_medio}</span>
          <span>
            Fase agregada: <strong className="text-white">{qGr.data.curva_banheira.fase_frota}</strong> • amostras:{" "}
            {qGr.data.curva_banheira.n_equipamentos_analisados ?? "—"}
          </span>
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        {["rt", "ht", "papel"].map((k) => (
          <button
            key={k}
            type="button"
            onClick={() => setAba(k)}
            className={`rounded-full border px-3 py-1 text-xs font-semibold ${
              aba === k ? "border-pcm-cyan bg-pcm-cyan/10 text-pcm-cyan" : "border-white/10 text-slate-400 hover:border-white/20"
            }`}
          >
            {k === "rt" ? "R(t)" : k === "ht" ? "h(t) — banheira" : "Papel Weibull"}
          </button>
        ))}
      </div>

      {aba === "rt" && (
        <div className="pcm-card h-[360px]">
          <h3 className="mb-2 text-base font-semibold text-slate-100">R(t) e h(t) no mesmo eixo temporal</h3>
          <ResponsiveContainer>
            <LineChart data={ptsRH}>
              <CartesianGrid stroke={CHART_COLORS.grid} />
              <XAxis dataKey="t" {...AXIS_STYLE} name="t" />
              <YAxis yAxisId="left" {...AXIS_STYLE} domain={[0, 1]} />
              <YAxis yAxisId="right" orientation="right" {...AXIS_STYLE} />
              <Tooltip {...TOOLTIP_STYLE} />
              <ReferenceLine y={0.7} stroke={CHART_COLORS.muted} strokeDasharray="4 4" label={{ value: "Meta 70%", fill: "#94A3B8" }} />
              <Line yAxisId="left" type="monotone" dataKey="R" stroke={CHART_COLORS.primary} dot={false} strokeWidth={2} name="R(t)" />
              <Line yAxisId="right" type="monotone" dataKey="h" stroke={CHART_COLORS.secondary} dot={false} strokeWidth={2} name="h(t)" />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {aba === "ht" && (
        <div className="pcm-card h-[360px]">
          <h3 className="mb-2 text-base font-semibold text-slate-100">Taxa de falhas h(t)</h3>
          <ResponsiveContainer>
            <LineChart data={ptsH}>
              <CartesianGrid stroke={CHART_COLORS.grid} />
              <XAxis dataKey="t" {...AXIS_STYLE} />
              <YAxis {...AXIS_STYLE} />
              <Tooltip {...TOOLTIP_STYLE} />
              <Line type="monotone" dataKey="h" stroke={CHART_COLORS.secondary} dot={false} strokeWidth={2} name="h(t)" />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {aba === "papel" && modo === "equipamento" && (
        <div className="pcm-card h-[360px]">
          <h3 className="mb-2 text-base font-semibold text-slate-100">Papel de Weibull (ln t vs posição do percentil)</h3>
          <ResponsiveContainer>
            <ComposedChart>
              <CartesianGrid stroke={CHART_COLORS.grid} />
              <XAxis dataKey="ln_t" type="number" {...AXIS_STYLE} name="ln t" />
              <YAxis dataKey="y" type="number" {...AXIS_STYLE} />
              <Tooltip {...TOOLTIP_STYLE} />
              <Scatter name="Observado" data={papelObs || []} fill={CHART_COLORS.primary} />
              <Line type="monotone" dataKey="y" data={papelAjust || []} stroke="#F97316" dot={false} name="Ajuste" />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      )}

      {aba === "papel" && modo === "grupo" && (
        <div className="pcm-card text-sm text-slate-400">Selecione um equipamento específico para ver o papel de Weibull dos intervalos observados.</div>
      )}
    </section>
  );
}
