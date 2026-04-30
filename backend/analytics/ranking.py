"""Ranking de criticidade de equipamentos."""

from analytics.kpis import calcular_kpis_equipamento


def gerar_ranking_criticos(df, top_n: int = 20):
    resultados = []
    for cod in df["cod_equipamento"].dropna().unique():
        df_ativo = df[df["cod_equipamento"] == cod]
        try:
            kpi = calcular_kpis_equipamento(df_ativo)
            resultados.append(
                {
                    "cod_equipamento": kpi.cod_equipamento,
                    "grupo": kpi.grupo,
                    "modelo": kpi.modelo,
                    "indice_criticidade": kpi.indice_criticidade,
                    "nivel_criticidade": kpi.nivel_criticidade,
                    "mttr_horas": kpi.mttr_horas,
                    "mtbf_horas": kpi.mtbf_horas,
                    "taxa_falhas_mes": kpi.taxa_falhas_mes,
                    "horas_parado_total": kpi.horas_parado_total,
                }
            )
        except Exception:
            continue
    return sorted(resultados, key=lambda x: x["indice_criticidade"], reverse=True)[:top_n]
