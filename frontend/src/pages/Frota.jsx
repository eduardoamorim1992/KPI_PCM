import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronRight } from "lucide-react";
import { getDashboardOpcoesFiltros, getEquipamentoHistorico, getEquipamentoKpis, getGrupoAnalise } from "../api";
import FilterBar from "../components/FilterBar";
import { useEquipamentos, useGrupos } from "../hooks/useFrota";

function CardGrupo({ g, expanded, onToggle }) {
  const analise = useQuery({
    queryKey: ["frota-grupo-analise", g.grupo_equipamento],
    enabled: expanded,
    queryFn: () => getGrupoAnalise(g.grupo_equipamento),
  });
  return (
    <button
      type="button"
      onClick={() => onToggle(g.grupo_equipamento)}
      className={`w-full rounded-xl border px-4 py-3 text-left transition ${
        expanded ? "border-pcm-cyan/40 bg-slate-900/70" : "border-white/[0.08] bg-pcm-card hover:border-white/15"
      }`}
    >
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-white">{g.grupo_equipamento}</p>
          <p className="text-xs text-slate-500">{g.equipamentos} ativos • {g.total_os} OS</p>
        </div>
        {expanded ? <ChevronDown className="h-4 w-4 text-pcm-cyan" /> : <ChevronRight className="h-4 w-4 text-slate-500" />}
      </div>
      {expanded && (
        <div className="mt-3 rounded-lg border border-white/5 bg-slate-950/60 p-3 text-xs text-slate-300">
          {analise.isFetching && "Carregando KPIs consolidados..."}
          {analise.data?.kpis && (
            <>
              <p>Hr parados (total): <span className="font-mono text-white">{analise.data.kpis.total_horas_parado}</span></p>
              <p>Falhas reais: <span className="font-mono text-white">{analise.data.kpis.total_falhas_reais}</span></p>
              <p>Top falha típica: <span className="font-mono text-amber-200">{analise.data.kpis.tipo_falha_mais_frequente}</span></p>
            </>
          )}
        </div>
      )}
      {analise.error && (
        <p className="mt-2 text-xs text-red-300">Detalhes do grupo indisponíveis.</p>
      )}
    </button>
  );
}

export default function Frota() {
  const [grupo, setGrupo] = useState("");
  const [frota, setFrota] = useState("");
  const [modelo, setModelo] = useState("");
  const equipQ = useEquipamentos({ grupo: grupo || undefined, frota: frota || undefined, modelo: modelo || undefined });
  const gruposQ = useGrupos();
  const opcoesQ = useQuery({
    queryKey: ["frota-opcoes", grupo, frota],
    queryFn: () => getDashboardOpcoesFiltros({ grupo: grupo || undefined, frota: frota ? Number(frota) : undefined }),
  });

  const [expandGrupo, setExpandGrupo] = useState(null);
  const [painelCod, setPainelCod] = useState(null);

  const historico = useQuery({
    queryKey: ["equipamento-historico", painelCod],
    enabled: Boolean(painelCod),
    queryFn: () => getEquipamentoHistorico(painelCod),
  });
  const kpisRow = useQuery({
    queryKey: ["equipamento-kpis", painelCod],
    enabled: Boolean(painelCod),
    queryFn: () => getEquipamentoKpis(painelCod),
  });

  const listaEquip = useMemo(() => {
    const rows = [...(equipQ.data ?? [])];
    rows.sort((a, b) => Number(b.total_os || 0) - Number(a.total_os || 0));
    return rows;
  }, [equipQ.data]);
  const gruposCards = useMemo(() => {
    const rows = gruposQ.data || [];
    return grupo ? rows.filter((g) => g.grupo_equipamento === grupo) : rows;
  }, [gruposQ.data, grupo]);

  return (
    <section className="relative space-y-4">
      <h2 className="text-xl font-semibold text-white">Gestão da frota</h2>

      <FilterBar>
        <select
          className="pcm-input min-w-[220px]"
          value={grupo}
          onChange={(e) => {
            setGrupo(e.target.value);
            setFrota("");
            setModelo("");
          }}
        >
          <option value="">Todos os grupos</option>
          {(gruposQ.data || []).map((g) => (
            <option key={g.grupo_equipamento} value={g.grupo_equipamento}>
              {g.grupo_equipamento}
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
        <select className="pcm-input min-w-[240px]" value={modelo} onChange={(e) => setModelo(e.target.value)} disabled={!grupo}>
          <option value="">{grupo ? "Todos os modelos" : "Selecione grupo"}</option>
          {(opcoesQ.data?.modelos || []).map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </select>
      </FilterBar>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {gruposCards.map((g) => (
          <CardGrupo
            key={g.grupo_equipamento}
            g={g}
            expanded={expandGrupo === g.grupo_equipamento}
            onToggle={(nome) => setExpandGrupo((cur) => (cur === nome ? null : nome))}
          />
        ))}
      </div>

      <div className="pcm-card overflow-x-auto">
        <h3 className="mb-3 text-base font-semibold text-slate-100">Equipamentos</h3>
        {equipQ.isLoading && <p className="text-sm text-slate-500">Carregando equipamentos...</p>}
        <table className="w-full min-w-[720px] text-sm">
          <thead>
            <tr className="border-b border-white/10 text-left text-xs uppercase text-slate-500">
              <th className="py-2">Código</th>
              <th>Modelo</th>
              <th>Grupo</th>
              <th className="text-right">Total OS</th>
              <th className="text-right">Ações</th>
            </tr>
          </thead>
          <tbody>
            {listaEquip.slice(0, 600).map((e) => (
              <tr key={`${e.cod_equipamento}`} className="border-b border-white/5">
                <td className="py-2 font-mono">{e.cod_equipamento}</td>
                <td className="max-w-[240px] truncate">{e.modelo}</td>
                <td>{e.grupo_equipamento}</td>
                <td className="text-right font-mono">{e.total_os}</td>
                <td className="text-right">
                  <button type="button" className="text-xs font-semibold text-pcm-cyan hover:underline" onClick={() => setPainelCod(e.cod_equipamento)}>
                    Histórico
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {painelCod && (
        <aside className="fixed inset-y-0 right-0 z-40 w-full max-w-md border-l border-white/10 bg-slate-950/95 p-4 shadow-2xl backdrop-blur-md">
          <div className="mb-4 flex items-center justify-between gap-3">
            <div>
              <p className="text-xs uppercase text-slate-500">Equipamento</p>
              <p className="font-mono text-xl text-white">{painelCod}</p>
              {kpisRow.data && (
                <p className="text-xs text-slate-400">
                  MTBF {kpisRow.data.mtbf_horas ?? "—"} h • MTTR {kpisRow.data.mttr_horas ?? "—"} h • DM{" "}
                  {kpisRow.data.disponibilidade_pct ?? "—"}%
                </p>
              )}
            </div>
            <button type="button" className="rounded-lg border border-white/10 px-3 py-1 text-xs text-slate-200" onClick={() => setPainelCod(null)}>
              Fechar
            </button>
          </div>
          <div className="max-h-[70vh] space-y-2 overflow-y-auto pr-2 text-xs">
            {historico.isLoading && <p className="text-slate-500">Carregando...</p>}
            {(historico.data || []).map((os) => (
              <article key={`${os.num_os}-${os.dt_entrada}`} className="rounded-lg border border-white/5 bg-slate-900/70 p-2">
                <p className="font-mono text-[11px] text-slate-400">
                  OS {os.num_os} • {os.dt_entrada}
                </p>
                <p className="text-slate-200">{os.descricao_servico}</p>
              </article>
            ))}
          </div>
        </aside>
      )}
      {painelCod && (
        <button type="button" className="fixed inset-0 z-30 bg-black/40" aria-label="Fechar painel" onClick={() => setPainelCod(null)} />
      )}
    </section>
  );
}
