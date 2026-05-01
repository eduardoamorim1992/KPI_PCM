// Modo estático: lê `public/data_pcm.json` gerado no build (sem backend).
let _cache = null;

const FALHAS_CORRETIVAS_REAIS = new Set([
  "FALHA MECANICA",
  "FALHA ELETRICA",
  "FALHA HIDRAULICA",
  "FALHA LUBRIFICACAO",
  "DESGASTE NATURAL",
  "FALHA EM PNEUS",
  "OBSTACULO PROCESSO",
  "FALHA OPERACIONAL",
  "PANE SECA/FALTA COMB",
  "ACIDENTE",
]);

function toDate(v) {
  if (!v) return null;
  const d = new Date(v);
  return Number.isFinite(d.getTime()) ? d : null;
}

function monthKey(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  return `${y}-${m}`;
}

function clampPct(v) {
  return Math.max(0, Math.min(100, v));
}

async function getDataset() {
  if (_cache) return _cache;
  const res = await fetch("/data_pcm.json", { cache: "force-cache" });
  if (!res.ok) throw new Error("Falha ao carregar data_pcm.json");
  const data = await res.json();
  _cache = data;
  return data;
}

function applyFilters(rows, params = {}) {
  const {
    grupo,
    unidade,
    frota,
    modelo,
    dt_inicio,
    dt_fim,
    tipo_falha,
  } = params || {};

  const di = dt_inicio ? toDate(dt_inicio) : null;
  const df = dt_fim ? toDate(dt_fim) : null;

  return rows.filter((r) => {
    if (grupo && r.grupo_equipamento !== String(grupo).toUpperCase()) return false;
    if (unidade && r.unidade !== String(unidade).toUpperCase()) return false;
    if (frota != null && String(r.cod_equipamento) !== String(frota)) return false;
    if (modelo && r.modelo !== String(modelo).toUpperCase()) return false;
    if (tipo_falha && r.tipo_falha !== String(tipo_falha).toUpperCase()) return false;

    const d = toDate(r.dt_entrada);
    if (!d) return false;
    if (di && d < di) return false;
    if (df) {
      // incluir dia final
      const dfEnd = new Date(df);
      dfEnd.setHours(23, 59, 59, 999);
      if (d > dfEnd) return false;
    }
    return true;
  });
}

function aggregateGrupos(rows) {
  const by = new Map();
  for (const r of rows) {
    const g = r.grupo_equipamento || "SEM_GRUPO";
    const cur = by.get(g) || { grupo_equipamento: g, total_os: 0, equipamentosSet: new Set(), horas_parado: 0 };
    cur.total_os += 1;
    cur.equipamentosSet.add(String(r.cod_equipamento));
    cur.horas_parado += Number(r.horas_parado || 0);
    by.set(g, cur);
  }
  return [...by.values()].map((x) => ({
    grupo_equipamento: x.grupo_equipamento,
    total_os: x.total_os,
    equipamentos: x.equipamentosSet.size,
    horas_parado: Math.round(x.horas_parado * 10) / 10,
  }));
}

function aggregateEquipamentos(rows, { grupo } = {}) {
  const filtered = grupo ? rows.filter((r) => r.grupo_equipamento === String(grupo).toUpperCase()) : rows;
  const by = new Map();
  for (const r of filtered) {
    const key = String(r.cod_equipamento);
    const cur =
      by.get(key) || {
        cod_equipamento: Number(r.cod_equipamento),
        modelo: r.modelo || "",
        marca: r.marca || "",
        grupo_equipamento: r.grupo_equipamento || "",
        ano_fabricacao: r.ano_fabricacao ?? null,
        unidade_medida: r.unidade_medida || "",
        total_os: 0,
        ultima_os: null,
      };
    cur.total_os += 1;
    const d = toDate(r.dt_entrada);
    if (d && (!cur.ultima_os || d > cur.ultima_os)) cur.ultima_os = d;
    by.set(key, cur);
  }
  return [...by.values()].map((x) => ({ ...x, ultima_os: x.ultima_os ? x.ultima_os.toISOString() : null }));
}

function mttrMtbfPorGrupo(rows) {
  const byGrupo = new Map();
  for (const r of rows) {
    const g = r.grupo_equipamento || "SEM_GRUPO";
    const cur = byGrupo.get(g) || new Map(); // cod -> { falhaHoras: [], falhaDates: [] }
    const cod = String(r.cod_equipamento);
    const x = cur.get(cod) || { falhaHoras: [], falhaDates: [] };
    if (r.is_falha_real) {
      x.falhaHoras.push(Number(r.horas_parado || 0));
      const d = toDate(r.dt_entrada);
      if (d) x.falhaDates.push(d);
    }
    cur.set(cod, x);
    byGrupo.set(g, cur);
  }

  const out = [];
  for (const [grupo, m] of byGrupo.entries()) {
    const mttrs = [];
    const mtbfs = [];
    for (const { falhaHoras, falhaDates } of m.values()) {
      if (falhaHoras.length) {
        const avg = falhaHoras.reduce((a, b) => a + b, 0) / falhaHoras.length;
        mttrs.push(avg);
      }
      if (falhaDates.length >= 2) {
        falhaDates.sort((a, b) => a - b);
        const diffs = [];
        for (let i = 1; i < falhaDates.length; i += 1) diffs.push((falhaDates[i] - falhaDates[i - 1]) / 3600000);
        const avg = diffs.reduce((a, b) => a + b, 0) / diffs.length;
        if (Number.isFinite(avg) && avg > 0) mtbfs.push(avg);
      }
    }
    out.push({
      grupo: String(grupo),
      mttr_medio: mttrs.length ? Math.round((mttrs.reduce((a, b) => a + b, 0) / mttrs.length) * 100) / 100 : 0,
      mtbf_medio: mtbfs.length ? Math.round((mtbfs.reduce((a, b) => a + b, 0) / mtbfs.length) * 100) / 100 : 0,
      n_equipamentos: m.size,
    });
  }
  return out.sort((a, b) => a.grupo.localeCompare(b.grupo));
}

function falhasStackPorMes(rows) {
  const fal = rows.filter((r) => r.is_falha_real);
  if (!fal.length) return { meses_linhas: [], tipos: [] };

  const tiposSet = new Set();
  const byMes = new Map();
  for (const r of fal) {
    tiposSet.add(String(r.tipo_falha || ""));
    const d = toDate(r.dt_entrada);
    if (!d) continue;
    const mes = monthKey(d);
    const cur = byMes.get(mes) || { mes };
    const t = String(r.tipo_falha || "");
    cur[t] = (cur[t] || 0) + 1;
    byMes.set(mes, cur);
  }
  const tipos = [...tiposSet].filter(Boolean).sort();
  const meses_linhas = [...byMes.values()].sort((a, b) => a.mes.localeCompare(b.mes));
  // garantir chaves
  for (const ln of meses_linhas) for (const t of tipos) ln[t] = ln[t] || 0;
  return { meses_linhas, tipos };
}

function composicaoOrigemPorGrupo(rows) {
  const by = new Map();
  for (const r of rows) {
    const g = r.grupo_equipamento || "SEM_GRUPO";
    const cur = by.get(g) || { grupo: g, total: 0, corretiva: 0, programada: 0, terceirizada: 0, outros: 0 };
    cur.total += 1;
    if (r.tipo_manutencao === "CORRETIVA") cur.corretiva += 1;
    else if (r.tipo_manutencao === "PROGRAMADA") cur.programada += 1;
    else if (r.tipo_manutencao === "TERCEIRIZADA") cur.terceirizada += 1;
    else cur.outros += 1;
    by.set(g, cur);
  }
  return [...by.values()]
    .map((x) => {
      const n = x.total || 1;
      return {
        grupo: String(x.grupo),
        pct_corretiva: Math.round((x.corretiva / n) * 1000) / 10,
        pct_programada: Math.round((x.programada / n) * 1000) / 10,
        pct_terceirizada: Math.round((x.terceirizada / n) * 1000) / 10,
        pct_outros: Math.round((x.outros / n) * 1000) / 10,
      };
    })
    .sort((a, b) => a.grupo.localeCompare(b.grupo));
}

function evolucaoMttrMensal(rows) {
  const fal = rows.filter((r) => r.is_falha_real);
  const byMes = new Map();
  for (const r of fal) {
    const d = toDate(r.dt_entrada);
    if (!d) continue;
    const mes = monthKey(d);
    const cur = byMes.get(mes) || { mes, soma: 0, n: 0 };
    cur.soma += Number(r.horas_parado || 0);
    cur.n += 1;
    byMes.set(mes, cur);
  }
  return [...byMes.values()]
    .sort((a, b) => a.mes.localeCompare(b.mes))
    .map((x) => ({ mes: x.mes, mttr_medio: x.n ? Math.round((x.soma / x.n) * 100) / 100 : 0, qtd_falhas: x.n }));
}

function heatmapDMSemanas(rows, horasSemana = 168) {
  // proxy simples igual backend: DM semanal por grupo
  const byGrupo = new Map();
  for (const r of rows) {
    const g = r.grupo_equipamento || "SEM_GRUPO";
    const cur = byGrupo.get(g) || [];
    cur.push(r);
    byGrupo.set(g, cur);
  }

  const out = [];
  for (const [grupo, arr] of byGrupo.entries()) {
    const eqSet = new Set(arr.map((r) => String(r.cod_equipamento)));
    const nEq = eqSet.size;
    if (!nEq) continue;

    const byWeek = new Map();
    for (const r of arr) {
      const d = toDate(r.dt_entrada);
      if (!d) continue;
      // semana ISO simplificada: YYYY-Www pelo UTC
      const tmp = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
      const dayNum = (tmp.getUTCDay() + 6) % 7;
      tmp.setUTCDate(tmp.getUTCDate() - dayNum + 3);
      const firstThursday = new Date(Date.UTC(tmp.getUTCFullYear(), 0, 4));
      const week = 1 + Math.round((tmp - firstThursday) / 604800000);
      const key = `${tmp.getUTCFullYear()}-W${String(week).padStart(2, "0")}`;
      const cur = byWeek.get(key) || { hp: 0 };
      cur.hp += Number(r.horas_parado || 0);
      byWeek.set(key, cur);
    }

    for (const [semana, v] of byWeek.entries()) {
      const cap = Math.max(nEq * horasSemana, 1);
      const hp = Math.min(v.hp, cap);
      const dm = clampPct(((cap - hp) / cap) * 100);
      out.push({ grupo: String(grupo), semana, dm_approx: Math.round(dm * 10) / 10 });
    }
  }
  out.sort((a, b) => a.semana.localeCompare(b.semana));
  return out.slice(-60);
}

function rankingFalhasPorEquipo(rows, topN = 10) {
  const fal = rows.filter((r) => r.is_falha_real);
  const by = new Map();
  for (const r of fal) {
    const key = String(r.cod_equipamento);
    const cur = by.get(key) || { cod_equipamento: Number(r.cod_equipamento), frota: String(r.cod_equipamento), grupo: r.grupo_equipamento, modelo: r.modelo, n_falhas: 0 };
    cur.n_falhas += 1;
    by.set(key, cur);
  }
  return [...by.values()].sort((a, b) => b.n_falhas - a.n_falhas).slice(0, topN);
}

function backlogAging(rows) {
  const ab = rows.filter((r) => String(r.status_os || "").includes("ABER") || String(r.status_os || "").includes("PEND"));
  if (!ab.length) return { kpis: { total_abertas: 0, idade_media_dias: 0 }, faixas: [] };
  const now = new Date();
  function faixa(dias) {
    if (dias <= 7) return "0-7";
    if (dias <= 15) return "8-15";
    if (dias <= 30) return "16-30";
    if (dias <= 60) return "31-60";
    return ">60";
  }
  const buckets = new Map();
  const ages = [];
  for (const r of ab) {
    const d = toDate(r.dt_entrada);
    if (!d) continue;
    const dias = Math.max(0, Math.floor((now - d) / 86400000));
    ages.push(dias);
    const f = faixa(dias);
    buckets.set(f, (buckets.get(f) || 0) + 1);
  }
  ages.sort((a, b) => a - b);
  const p90 = ages.length ? ages[Math.floor(0.9 * (ages.length - 1))] : 0;
  const media = ages.length ? ages.reduce((a, b) => a + b, 0) / ages.length : 0;
  const pct30 = ages.length ? (ages.filter((x) => x > 30).length / ages.length) * 100 : 0;
  const ordem = ["0-7", "8-15", "16-30", "31-60", ">60"];
  return {
    kpis: {
      total_abertas: ages.length,
      idade_media_dias: Math.round(media * 10) / 10,
      idade_p90_dias: Math.round(p90 * 10) / 10,
      pct_maior_30d: Math.round(pct30 * 10) / 10,
    },
    faixas: ordem.map((f) => ({ faixa: f, qtd_os: buckets.get(f) || 0 })),
  };
}

function criticidadeABC(rows, topN = 20) {
  const by = new Map();
  for (const r of rows) {
    const key = String(r.cod_equipamento);
    const cur =
      by.get(key) || {
        cod_equipamento: Number(r.cod_equipamento),
        frota: String(r.cod_equipamento),
        grupo: r.grupo_equipamento,
        modelo: r.modelo,
        total_os: 0,
        falhas_reais: 0,
        impacto_horas: 0,
        mttr_sum: 0,
        mttr_n: 0,
      };
    cur.total_os += 1;
    cur.impacto_horas += Number(r.horas_parado || 0);
    if (r.is_falha_real) {
      cur.falhas_reais += 1;
      cur.mttr_sum += Number(r.horas_parado || 0);
      cur.mttr_n += 1;
    }
    by.set(key, cur);
  }
  const base = [...by.values()].map((x) => ({ ...x, mttr_horas: x.mttr_n ? x.mttr_sum / x.mttr_n : 0 }));
  const maxImp = Math.max(...base.map((x) => x.impacto_horas), 0);
  const maxFal = Math.max(...base.map((x) => x.falhas_reais), 0);
  const maxMttr = Math.max(...base.map((x) => x.mttr_horas), 0);
  for (const x of base) {
    const imp = maxImp ? (x.impacto_horas / maxImp) * 100 : 0;
    const fre = maxFal ? (x.falhas_reais / maxFal) * 100 : 0;
    const mttr = maxMttr ? (x.mttr_horas / maxMttr) * 100 : 0;
    x.score_criticidade = Math.round((imp * 0.4 + fre * 0.35 + mttr * 0.25) * 10) / 10;
  }
  base.sort((a, b) => b.score_criticidade - a.score_criticidade);
  const totalScore = base.reduce((a, b) => a + b.score_criticidade, 0) || 1;
  let acc = 0;
  for (const x of base) {
    acc += x.score_criticidade;
    const pct = (acc / totalScore) * 100;
    x.classe_abc = pct <= 80 ? "A" : pct <= 95 ? "B" : "C";
    x.mttr_horas = Math.round(x.mttr_horas * 10) / 10;
    x.impacto_horas = Math.round(x.impacto_horas * 10) / 10;
  }
  return base.slice(0, topN).map((x) => ({
    cod_equipamento: x.cod_equipamento,
    frota: x.frota,
    grupo: x.grupo,
    modelo: x.modelo,
    total_os: x.total_os,
    falhas_reais: x.falhas_reais,
    impacto_horas: x.impacto_horas,
    mttr_horas: x.mttr_horas,
    score_criticidade: x.score_criticidade,
    classe_abc: x.classe_abc,
  }));
}

export async function getDashboardResumo(params = {}) {
  const ds = await getDataset();
  const rows = applyFilters(ds.rows || [], params);
  if (!rows.length) throw new Error("Nenhum dado encontrado para os filtros");

  const falhasReais = rows.filter((r) => r.is_falha_real).length;
  const totalOS = rows.length;

  // aberto/encerrado (proxy)
  const encerradas = rows.filter((r) => Boolean(r.dt_saida) || String(r.status_os || "").includes("ENCER")).length;
  const abertas = totalOS - encerradas;

  const dts = rows.map((r) => toDate(r.dt_entrada)).filter(Boolean);
  dts.sort((a, b) => a - b);
  const periodoDias = dts.length ? Math.max(1, Math.round((dts[dts.length - 1] - dts[0]) / 86400000)) : 30;
  const periodoHoras = periodoDias * 24;

  const eqSet = new Set(rows.map((r) => String(r.cod_equipamento)));
  const nEq = eqSet.size || 1;
  const hpTotal = rows.reduce((a, r) => a + Number(r.horas_parado || 0), 0);
  const cap = Math.max(nEq * periodoHoras, 1);
  const dm = clampPct(((cap - Math.min(hpTotal, cap)) / cap) * 100);

  // % corretivas
  const nCorretiva = rows.filter((r) => r.tipo_manutencao === "CORRETIVA").length;
  const pctCorretiva = totalOS ? Math.round((nCorretiva / totalOS) * 1000) / 10 : 0;

  // MTTR médio simples (falhas reais)
  const falRows = rows.filter((r) => r.is_falha_real);
  const mttrMedio = falRows.length ? falRows.reduce((a, r) => a + Number(r.horas_parado || 0), 0) / falRows.length : 0;

  // OS vs mês anterior (MoM) pelo filtro
  const byMesOS = new Map();
  for (const r of rows) {
    const d = toDate(r.dt_entrada);
    if (!d) continue;
    const mes = monthKey(d);
    byMesOS.set(mes, (byMesOS.get(mes) || 0) + 1);
  }
  const mesesOS = [...byMesOS.keys()].sort();
  let variacaoMoM = null;
  if (mesesOS.length >= 2) {
    const last = byMesOS.get(mesesOS[mesesOS.length - 1]) || 0;
    const prev = byMesOS.get(mesesOS[mesesOS.length - 2]) || 0;
    variacaoMoM = prev > 0 ? Math.round(((last - prev) / prev) * 100) : null;
  }

  // falhas por tipo
  const falhasVc = new Map();
  for (const r of rows) {
    if (!r.is_falha_real) continue;
    const t = String(r.tipo_falha || "");
    falhasVc.set(t, (falhasVc.get(t) || 0) + 1);
  }
  const tiposOrdenados = [...falhasVc.entries()].sort((a, b) => b[1] - a[1]).map((x) => x[0]);
  const preferidas = ["FALHA MECANICA", "DESGASTE NATURAL", "FALHA EM PNEUS", "FALHA ELETRICA"].filter((t) => falhasVc.has(t));
  const tiposSeries = [...new Set([...preferidas, ...tiposOrdenados])].slice(0, 6);

  // serie mensal stack
  const byMes = new Map();
  for (const r of rows) {
    if (!r.is_falha_real) continue;
    const d = toDate(r.dt_entrada);
    if (!d) continue;
    const mes = monthKey(d);
    const cur = byMes.get(mes) || { mes };
    const t = tiposSeries.includes(r.tipo_falha) ? r.tipo_falha : "OUTRAS";
    cur[t] = (cur[t] || 0) + 1;
    byMes.set(mes, cur);
  }
  const meses = [...byMes.values()].sort((a, b) => a.mes.localeCompare(b.mes));
  const tipos = [...tiposSeries, "OUTRAS"].filter((t, idx, arr) => arr.indexOf(t) === idx);
  for (const ln of meses) for (const t of tipos) ln[t] = ln[t] || 0;

  // falhas por tipo (donut)
  const falhasPorTipo = [...falhasVc.entries()].sort((a, b) => b[1] - a[1]).slice(0, 10).map(([tipo, qtd]) => ({ tipo, qtd }));

  return {
    periodo: { inicio: dts[0]?.toISOString?.() || null, fim: dts[dts.length - 1]?.toISOString?.() || null, dias: periodoDias },
    totais: {
      total_os: totalOS,
      total_equipamentos: nEq,
      falhas_reais: falhasReais,
    },
    kpis: {
      os_abertas_periodo: abertas,
      os_encerradas_periodo: encerradas,
      dm_frota_media_pct: Math.round(dm * 10) / 10,
      mttr_medio_horas: Math.round(mttrMedio * 10) / 10,
      mtbf_medio_horas: 0,
      taxa_falhas_mes: 0,
      custo_mom_pct: 0,
      variacao_os_mom_pct: variacaoMoM,
      equipamentos_em_manutencao: 0,
      pct_corretiva: pctCorretiva,
    },
    falhas_por_tipo: falhasPorTipo,
    os_por_grupo: aggregateGrupos(rows).map((g) => ({ grupo: g.grupo_equipamento, total_os: g.total_os })),
    disponibilidade_por_grupo: aggregateGrupos(rows).map((g) => ({
      grupo: g.grupo_equipamento,
      n_equipamentos: g.equipamentos,
      horas_parado: g.horas_parado,
      horas_totais: g.equipamentos * periodoHoras,
      disponibilidade_pct: clampPct(((g.equipamentos * periodoHoras - Math.min(g.horas_parado, g.equipamentos * periodoHoras)) / (g.equipamentos * periodoHoras || 1)) * 100),
      meta_dm_pct: 80,
      status: "OK",
    })),
    os_mensal_por_falha: { meses_linhas: meses, tipos },
  };
}

export async function getRanking(top_n = 10, grupo) {
  const ds = await getDataset();
  const rows = applyFilters(ds.rows || [], grupo ? { grupo } : {});
  const by = new Map();
  for (const r of rows) {
    const key = String(r.cod_equipamento);
    const cur = by.get(key) || { cod_equipamento: Number(r.cod_equipamento), grupo: r.grupo_equipamento, modelo: r.modelo, indice_criticidade: 0, nivel_criticidade: "MEDIO", horas_parado_total: 0, taxa_falhas_mes: 0, mttr_horas: 0, mtbf_horas: 0 };
    cur.horas_parado_total += Number(r.horas_parado || 0);
    cur.indice_criticidade += (r.is_falha_real ? 2 : 0.5) + Number(r.horas_parado || 0) * 0.02;
    by.set(key, cur);
  }
  const out = [...by.values()].sort((a, b) => b.indice_criticidade - a.indice_criticidade).slice(0, top_n);
  return out.map((x) => ({ ...x, indice_criticidade: Math.round(x.indice_criticidade * 10) / 10 }));
}

export async function getDashboardOpcoesFiltros({ grupo, unidade, frota } = {}) {
  const ds = await getDataset();
  const rows = ds.rows || [];

  const grupos = [...new Set(rows.map((r) => r.grupo_equipamento).filter(Boolean))].sort();
  const subset = applyFilters(rows, { grupo, unidade, frota });

  const frotasMap = new Map();
  for (const r of subset) {
    const cod = r.cod_equipamento;
    if (cod == null) continue;
    if (!frotasMap.has(String(cod))) frotasMap.set(String(cod), { cod_equipamento: Number(cod), modelo: r.modelo || "" });
  }

  const modelos = [...new Set(subset.map((r) => r.modelo).filter(Boolean))].sort();
  const tipos_falha = [...new Set(subset.map((r) => r.tipo_falha).filter(Boolean))].sort();

  return { grupos, frotas: [...frotasMap.values()].sort((a, b) => a.cod_equipamento - b.cod_equipamento), modelos, tipos_falha };
}

export async function getGrupos() {
  const ds = await getDataset();
  return aggregateGrupos(ds.rows || []);
}

export async function getEquipamentos({ grupo, frota, modelo } = {}) {
  const ds = await getDataset();
  let rows = aggregateEquipamentos(ds.rows || [], { grupo });
  if (frota) rows = rows.filter((r) => String(r.cod_equipamento) === String(frota));
  if (modelo) rows = rows.filter((r) => String(r.modelo) === String(modelo).toUpperCase());
  return rows;
}

export async function getAnaliticoOverview(params = {}) {
  const ds = await getDataset();
  const rows = applyFilters(ds.rows || [], params);
  if (!rows.length) throw new Error("Nenhum dado encontrado para os filtros");
  return {
    mtbf_mttr_por_grupo: mttrMtbfPorGrupo(rows),
    evolucao_mttr_mensal: evolucaoMttrMensal(rows),
    falhas_stack_mes: falhasStackPorMes(rows),
    composicao_origem: composicaoOrigemPorGrupo(rows),
    heatmap_dm: heatmapDMSemanas(rows),
    top_falhas_equip: rankingFalhasPorEquipo(rows, 10),
    criticidade_abc: criticidadeABC(rows, 20),
    backlog_aging: backlogAging(rows),
    filtros: { ...params },
  };
}

// Abaixo: funcionalidades avançadas exigem backend (Weibull/Monte Carlo).
// Mantemos as telas com mensagem amigável.
export async function getGrupoAnalise() {
  throw new Error("Indisponível no modo estático (sem backend).");
}
export async function getEquipamentoKpis() {
  throw new Error("Indisponível no modo estático (sem backend).");
}
export async function getEquipamentoHistorico() {
  throw new Error("Indisponível no modo estático (sem backend).");
}
export async function getUsoAtualEquipamento() {
  throw new Error("Indisponível no modo estático (sem backend).");
}
export async function getConfiabilidadeEquipamento() {
  throw new Error("Indisponível no modo estático (sem backend).");
}
export async function postMonteCarlo() {
  throw new Error("Indisponível no modo estático (sem backend).");
}
export async function getSimulacaoFrota() {
  throw new Error("Indisponível no modo estático (sem backend).");
}
