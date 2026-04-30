"""
Calculo de KPIs do PCM.
"""

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd


@dataclass
class KPIResult:
    cod_equipamento: Optional[int]
    grupo: str
    modelo: str
    periodo_dias: int
    total_os: int
    os_falhas_reais: int
    os_programadas: int
    os_terceirizadas: int
    horas_parado_total: float
    horas_parado_falhas: float
    horas_operativas_estimadas: float
    mtbf_horas: float
    mtbf_km_hr: Optional[float]
    mttr_horas: float
    disponibilidade_pct: float
    taxa_falhas_mes: float
    backlog_os: int
    pct_corretiva: float
    pct_programada: float
    pct_terceirizada: float
    tipo_falha_predominante: str
    frequencia_falha_predominante: int
    indice_criticidade: float
    nivel_criticidade: str


def calcular_mtbf(df_falhas: pd.DataFrame) -> float:
    if len(df_falhas) < 2:
        return 0.0

    df = df_falhas.sort_values("dt_entrada").copy()
    intervalos = []
    for i in range(1, len(df)):
        fim_anterior = df["dt_saida"].iloc[i - 1]
        inicio_atual = df["dt_entrada"].iloc[i]
        if pd.isna(fim_anterior):
            horas_prev = df["horas_parado"].iloc[i - 1]
            fim_anterior = df["dt_entrada"].iloc[i - 1] + pd.Timedelta(hours=horas_prev)
        if pd.isna(inicio_atual) or pd.isna(fim_anterior):
            continue
        intervalo_h = (inicio_atual - fim_anterior).total_seconds() / 3600
        if intervalo_h >= 0:
            intervalos.append(intervalo_h)
    return float(np.mean(intervalos)) if intervalos else 0.0


def calcular_mtbf_por_uso(df_falhas: pd.DataFrame, unidade: str = "HM") -> Optional[float]:
    del unidade
    if len(df_falhas) < 2:
        return None
    df = df_falhas.sort_values("dt_entrada").copy()
    acumulados = df["acumulado_km_hr"].dropna()
    if len(acumulados) < 2:
        return None
    delta_uso = acumulados.max() - acumulados.min()
    n_intervalos = len(df_falhas) - 1
    if delta_uso <= 0 or n_intervalos == 0:
        return None
    return float(delta_uso / n_intervalos)


def calcular_indice_criticidade(
    n_falhas: int, horas_parado: float, dm_pct: float, taxa_mensal: float, periodo_dias: int
) -> float:
    del n_falhas, periodo_dias
    score_frequencia = min((taxa_mensal / 5.0) * 100, 100)
    score_dm = min(max(0, (85.0 - dm_pct) / 85.0 * 100), 100)
    score_horas = min((horas_parado / 200.0) * 100, 100)
    return float(min((score_frequencia * 0.40) + (score_dm * 0.35) + (score_horas * 0.25), 100))


def obter_meta_dm(grupo: str) -> float:
    metas = {
        "COLHEDORAS": 88.0,
        "CAMINHOES": 85.0,
        "TRATORES": 83.0,
        "IMPLEMENTOS AGRICOLAS": 80.0,
        "MAQUINAS PESADAS": 80.0,
        "IMPLEMENTOS RODOVIARIOS": 82.0,
        "VEICULOS LEVES": 90.0,
        "ONIBUS": 88.0,
        "MOTO BOMBA": 85.0,
        "QUADRICICLOS": 85.0,
    }
    return metas.get(grupo, 80.0)


def calcular_kpis_equipamento(df_ativo: pd.DataFrame, periodo_horas_totais: float = None) -> KPIResult:
    if len(df_ativo) == 0:
        raise ValueError("DataFrame vazio")
    df = df_ativo.sort_values("dt_entrada").copy()
    cod = df["cod_equipamento"].iloc[0]
    grupo = str(df["grupo_equipamento"].iloc[0])
    modelo = str(df["modelo"].iloc[0])

    dt_inicio = df["dt_entrada"].min()
    dt_fim = df["dt_saida"].dropna().max()
    if pd.isna(dt_fim):
        dt_fim = df["dt_entrada"].max()
    periodo_dias = max((dt_fim - dt_inicio).days, 1)
    periodo_horas = periodo_horas_totais if periodo_horas_totais else periodo_dias * 24

    total_os = len(df)
    df_falhas = df[df["is_falha_real"] == True]
    n_falhas = len(df_falhas)
    n_programadas = len(df[df["tipo_manutencao"] == "PROGRAMADA"])
    n_terceirizadas = len(df[df["tipo_manutencao"] == "TERCEIRIZADA"])
    mttr = float(df_falhas["horas_parado"].mean()) if n_falhas > 0 else 0.0
    mtbf = calcular_mtbf(df_falhas)
    unid = df["unidade_medida"].iloc[0] if "unidade_medida" in df.columns else "HM"
    mtbf_km_hr = calcular_mtbf_por_uso(df_falhas, unidade=unid)

    horas_parado_total = float(df["horas_parado"].fillna(0).sum())
    horas_parado_falhas = float(df_falhas["horas_parado"].fillna(0).sum())
    horas_operativas = max(float(periodo_horas - horas_parado_total), 0.0)
    dm = (horas_operativas / periodo_horas * 100) if periodo_horas > 0 else 0.0
    n_meses = max(periodo_dias / 30.44, 1)
    taxa_falhas_mes = n_falhas / n_meses

    pct_corretiva = len(df[df["tipo_manutencao"] == "CORRETIVA"]) / total_os * 100 if total_os else 0
    pct_programada = n_programadas / total_os * 100 if total_os else 0
    pct_terceirizada = n_terceirizadas / total_os * 100 if total_os else 0

    if n_falhas > 0:
        tipo_dom = df_falhas["tipo_falha"].value_counts()
        tipo_dom_nome = str(tipo_dom.index[0])
        tipo_dom_freq = int(tipo_dom.iloc[0])
    else:
        tipo_dom_nome = "N/A"
        tipo_dom_freq = 0

    criticidade = calcular_indice_criticidade(n_falhas, horas_parado_total, dm, taxa_falhas_mes, periodo_dias)
    niveis = [(25, "BAIXO"), (50, "MEDIO"), (75, "ALTO"), (101, "CRITICO")]
    nivel = next(n for lim, n in niveis if criticidade < lim)

    return KPIResult(
        cod_equipamento=int(cod) if pd.notna(cod) else None,
        grupo=grupo,
        modelo=modelo,
        periodo_dias=periodo_dias,
        total_os=total_os,
        os_falhas_reais=n_falhas,
        os_programadas=n_programadas,
        os_terceirizadas=n_terceirizadas,
        horas_parado_total=round(horas_parado_total, 2),
        horas_parado_falhas=round(horas_parado_falhas, 2),
        horas_operativas_estimadas=round(horas_operativas, 2),
        mtbf_horas=round(mtbf, 2),
        mtbf_km_hr=round(mtbf_km_hr, 1) if mtbf_km_hr else None,
        mttr_horas=round(mttr, 2),
        disponibilidade_pct=round(dm, 2),
        taxa_falhas_mes=round(taxa_falhas_mes, 2),
        backlog_os=0,
        pct_corretiva=round(pct_corretiva, 1),
        pct_programada=round(pct_programada, 1),
        pct_terceirizada=round(pct_terceirizada, 1),
        tipo_falha_predominante=tipo_dom_nome,
        frequencia_falha_predominante=tipo_dom_freq,
        indice_criticidade=round(criticidade, 1),
        nivel_criticidade=nivel,
    )


def calcular_kpis_grupo(df: pd.DataFrame, grupo: str) -> dict:
    df_grupo = df[df["grupo_equipamento"] == grupo].copy()
    if len(df_grupo) == 0:
        return {}
    total_os = len(df_grupo)
    n_equipamentos = int(df_grupo["cod_equipamento"].nunique())
    horas_total = float(df_grupo["horas_parado"].fillna(0).sum())
    n_falhas = int(df_grupo[df_grupo["is_falha_real"]]["num_os"].count())
    kpis_individuais = []
    for cod in df_grupo["cod_equipamento"].dropna().unique():
        try:
            kpis_individuais.append(calcular_kpis_equipamento(df_grupo[df_grupo["cod_equipamento"] == cod]))
        except Exception:
            continue
    return {
        "grupo": grupo,
        "n_equipamentos": n_equipamentos,
        "total_os": total_os,
        "total_falhas_reais": n_falhas,
        "total_horas_parado": round(horas_total, 1),
        "mttr_medio": round(float(df_grupo["horas_parado"].mean()), 2) if total_os else 0.0,
        "os_por_equipamento_mes": round(total_os / max(n_equipamentos, 1) / 12, 1),
        "pct_corretiva": round(len(df_grupo[df_grupo["tipo_manutencao"] == "CORRETIVA"]) / total_os * 100, 1)
        if total_os
        else 0.0,
        "tipo_falha_mais_frequente": df_grupo[df_grupo["is_falha_real"]]["tipo_falha"].mode().iloc[0]
        if n_falhas > 0
        else "N/A",
        "ranking_criticos": sorted(kpis_individuais, key=lambda x: x.indice_criticidade, reverse=True)[:10],
    }


def calcular_disponibilidade_frota(df: pd.DataFrame, periodo_horas: float, grupos: list = None) -> pd.DataFrame:
    if grupos:
        df = df[df["grupo_equipamento"].isin(grupos)]

    resultado = []
    for grupo, grp in df.groupby("grupo_equipamento"):
        n_equip = int(grp["cod_equipamento"].nunique())
        horas_parado = float(grp["horas_parado"].fillna(0).sum())
        horas_totais = n_equip * periodo_horas
        dm = max((horas_totais - horas_parado) / horas_totais * 100, 0) if horas_totais > 0 else 0
        resultado.append(
            {
                "grupo": grupo,
                "n_equipamentos": n_equip,
                "horas_parado": round(horas_parado, 1),
                "horas_totais": round(horas_totais, 1),
                "disponibilidade_pct": round(dm, 2),
                "meta_dm_pct": obter_meta_dm(grupo),
            }
        )
    out = pd.DataFrame(resultado)
    if out.empty:
        return out
    out["status"] = out.apply(
        lambda r: "ACIMA_META" if r["disponibilidade_pct"] >= r["meta_dm_pct"] else "ABAIXO_META", axis=1
    )
    return out.sort_values("disponibilidade_pct")
