import axios from "axios";

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || "",
  timeout: 15000,
});

export async function getDashboardResumo(params = {}) {
  const { data } = await api.get("/api/dashboard/resumo", { params });
  return data;
}

export async function getRanking(top_n = 10, grupo) {
  const { data } = await api.get("/api/dashboard/ranking-criticos", { params: { top_n, grupo } });
  return data;
}

export async function getAnaliticoOverview(params = {}) {
  const { data } = await api.get("/api/analitico/overview", { params });
  return data;
}

export async function getDashboardOpcoesFiltros({ grupo, unidade, frota } = {}) {
  const { data } = await api.get("/api/dashboard/opcoes-filtros", { params: { grupo, unidade, frota } });
  return data;
}

export async function getGrupos() {
  const { data } = await api.get("/api/grupos");
  return data;
}

export async function getEquipamentos({ grupo, frota, modelo } = {}) {
  const { data } = await api.get("/api/filtros/equipamentos", { params: { grupo } });
  let rows = data;
  if (frota) rows = rows.filter((r) => String(r.cod_equipamento) === String(frota));
  if (modelo) rows = rows.filter((r) => String(r.modelo) === String(modelo));
  return rows;
}

export async function getGrupoAnalise(grupo) {
  const { data } = await api.get(`/api/grupos/${encodeURIComponent(grupo)}/analise`);
  return data;
}

export async function getEquipamentoKpis(cod) {
  const { data } = await api.get(`/api/equipamentos/${cod}/kpis`);
  return data;
}

export async function getEquipamentoHistorico(cod) {
  const { data } = await api.get(`/api/equipamentos/${cod}/historico`);
  return data;
}

export async function getUsoAtualEquipamento(cod) {
  const { data } = await api.get(`/api/equipamentos/${cod}/uso-atual`);
  return data;
}

export async function getConfiabilidadeEquipamento(cod) {
  const { data } = await api.get(`/api/equipamentos/${cod}/confiabilidade`);
  return data;
}

export async function postMonteCarlo(cod, { horimetro_atual = 0, n_simulacoes = 10000, horizonte_horas = 2160 }) {
  const { data } = await api.post(`/api/simulacao/monte-carlo/${cod}`, null, {
    params: { horimetro_atual, n_simulacoes, horizonte_horas },
  });
  return data;
}

export async function getSimulacaoFrota(grupo, n_simulacoes = 8000) {
  const { data } = await api.get("/api/simulacao/frota", { params: { grupo, n_simulacoes } });
  return data;
}
