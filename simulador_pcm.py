from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd


RENAME_MAP = {
    "INSTANCIA": "unidade",
    "NO_BOLETIM": "os_numero",
    "CD_EQUIPTO": "equipamento_id",
    "FG_ORIGEM": "origem_os",
    "DE_MOTENTR": "tipo_falha",
    "DT_ENTRADA": "dt_parada",
    "DT_SAIDA": "dt_retorno",
    "DE_SERVICO": "descricao_servico",
    "ACM_KM_HR": "km_hr_acumulado",
    "DE_MODELO": "modelo",
    "DE_MARCA": "marca",
    "NO_ANOFABR": "ano_fabricacao",
    "DE_GRUPO_OP": "tipo_equipamento",
    "CD_UNIMED": "tipo_deslocamento",
}


@dataclass
class JanelaAnalise:
    nome: str
    dias: int


def normalizar_codigo_numerico(valor: object) -> str:
    if pd.isna(valor):
        return "N/A"
    texto = str(valor).strip()
    if texto == "" or texto.lower() == "nan":
        return "N/A"
    if texto.endswith(".0"):
        texto = texto[:-2]
    return texto


def carregar_dados(path_excel: Path) -> pd.DataFrame:
    df = pd.read_excel(path_excel)
    df = df.rename(columns=RENAME_MAP)

    colunas_esperadas = [
        "unidade",
        "os_numero",
        "equipamento_id",
        "origem_os",
        "tipo_falha",
        "dt_parada",
        "dt_retorno",
        "descricao_servico",
        "km_hr_acumulado",
        "modelo",
        "marca",
        "ano_fabricacao",
        "tipo_equipamento",
    ]
    faltantes = [c for c in colunas_esperadas if c not in df.columns]
    if faltantes:
        raise ValueError(f"Colunas ausentes na planilha: {faltantes}")

    df["dt_parada"] = pd.to_datetime(df["dt_parada"], errors="coerce")
    df["dt_retorno"] = pd.to_datetime(df["dt_retorno"], errors="coerce")
    df = df[df["dt_parada"].notna()].copy()

    df["duracao_h"] = (
        (df["dt_retorno"] - df["dt_parada"]).dt.total_seconds() / 3600.0
    ).clip(lower=0)

    # Completa retornos ausentes com mediana por tipo de falha.
    mediana_por_falha = df.groupby("tipo_falha")["duracao_h"].transform("median")
    df["duracao_h"] = df["duracao_h"].fillna(mediana_por_falha)
    df["duracao_h"] = df["duracao_h"].fillna(df["duracao_h"].median())
    df["origem_os"] = df["origem_os"].fillna("N/A")
    df["tipo_falha"] = df["tipo_falha"].fillna("N/A")
    if "tipo_deslocamento" in df.columns:
        df["tipo_deslocamento"] = df["tipo_deslocamento"].fillna("N/A")

    # Garante identificador consistente para agrupamentos e exibicao.
    df["equipamento_id"] = df["equipamento_id"].apply(normalizar_codigo_numerico)
    df["frota"] = df["equipamento_id"]

    return df


def extrair_causa_da_descricao(texto: object) -> str:
    if not isinstance(texto, str):
        return "N/A"
    upper = texto.upper()
    marcador = "CAUSA"
    if marcador not in upper:
        return "N/A"
    trecho = upper.split(marcador, 1)[1]
    for sep in ["//", "SINTOMA", "LOCAL", "SOLU", "PREVIS", "TEMPO"]:
        if sep in trecho:
            trecho = trecho.split(sep, 1)[0]
    trecho = trecho.replace(":", " ").replace(";", " ").strip(" -*")
    trecho = " ".join(trecho.split())
    return trecho if trecho else "N/A"


def calcular_mtbf_por_intervalo(df_janela: pd.DataFrame) -> pd.DataFrame:
    ordenado = df_janela.sort_values(["equipamento_id", "dt_parada"]).copy()
    ordenado["delta_h"] = (
        ordenado.groupby("equipamento_id")["dt_parada"]
        .diff()
        .dt.total_seconds()
        .div(3600.0)
    )
    return ordenado


def montar_kpis(df: pd.DataFrame, dias: int, referencia: pd.Timestamp) -> pd.DataFrame:
    inicio = referencia - pd.Timedelta(days=dias)
    df_janela = df[(df["dt_parada"] >= inicio) & (df["dt_parada"] <= referencia)].copy()
    if df_janela.empty:
        return pd.DataFrame()

    df_janela = calcular_mtbf_por_intervalo(df_janela)
    horas_periodo = dias * 24

    agrupado = (
        df_janela.groupby(["equipamento_id", "unidade", "modelo", "marca", "tipo_equipamento"])
        .agg(
            falhas=("os_numero", "count"),
            downtime_h=("duracao_h", "sum"),
            mttr_h=("duracao_h", "mean"),
            mtbf_intervalo_h=("delta_h", "mean"),
            ultima_falha=("dt_parada", "max"),
        )
        .reset_index()
    )

    # Fallback de MTBF quando ha poucas falhas para calcular intervalos.
    agrupado["mtbf_operacional_h"] = (horas_periodo - agrupado["downtime_h"]).clip(lower=0) / agrupado[
        "falhas"
    ].clip(lower=1)
    agrupado["mtbf_h"] = agrupado["mtbf_intervalo_h"].fillna(agrupado["mtbf_operacional_h"])
    agrupado["disponibilidade_pct"] = (
        agrupado["mtbf_h"] / (agrupado["mtbf_h"] + agrupado["mttr_h"]).replace(0, np.nan) * 100
    )
    agrupado["taxa_falha_por_dia"] = agrupado["falhas"] / max(dias, 1)

    colunas_saida = [
        "equipamento_id",
        "unidade",
        "modelo",
        "marca",
        "tipo_equipamento",
        "falhas",
        "downtime_h",
        "mttr_h",
        "mtbf_h",
        "disponibilidade_pct",
        "taxa_falha_por_dia",
        "ultima_falha",
    ]
    return agrupado[colunas_saida].sort_values(["falhas", "downtime_h"], ascending=False)


def simular_monte_carlo(
    df_12m: pd.DataFrame,
    referencia: pd.Timestamp,
    n_simulacoes: int = 10000,
    horizonte_dias: int = 30,
) -> pd.DataFrame:
    if df_12m.empty:
        return pd.DataFrame()

    rng = np.random.default_rng(42)
    historico = df_12m.copy()
    resultados = []

    global_duracao = historico["duracao_h"].dropna().values
    if len(global_duracao) == 0:
        global_duracao = np.array([1.0])

    for equip_id, g in historico.groupby("equipamento_id"):
        g = g.sort_values("dt_parada")
        falhas = len(g)
        lambda_por_dia = falhas / 365.0
        if lambda_por_dia <= 0:
            lambda_por_dia = 1 / 365.0

        duracoes = g["duracao_h"].dropna().values
        if len(duracoes) == 0:
            duracoes = global_duracao

        falhas_sim = rng.poisson(lam=lambda_por_dia * horizonte_dias, size=n_simulacoes)
        downtime_sim = np.zeros(n_simulacoes)
        for i, n_falhas in enumerate(falhas_sim):
            if n_falhas > 0:
                downtime_sim[i] = rng.choice(duracoes, size=n_falhas, replace=True).sum()

        prob_ao_menos_uma = float((falhas_sim >= 1).mean())
        resultados.append(
            {
                "equipamento_id": equip_id,
                "unidade": g["unidade"].iloc[0],
                "modelo": g["modelo"].iloc[0],
                "marca": g["marca"].iloc[0],
                "tipo_equipamento": g["tipo_equipamento"].iloc[0],
                "falhas_12m": falhas,
                "lambda_falha_dia": lambda_por_dia,
                "prob_parar_30d": prob_ao_menos_uma,
                "downtime_30d_esperado_h": float(downtime_sim.mean()),
                "downtime_30d_p50_h": float(np.quantile(downtime_sim, 0.50)),
                "downtime_30d_p90_h": float(np.quantile(downtime_sim, 0.90)),
                "downtime_30d_p95_h": float(np.quantile(downtime_sim, 0.95)),
                "ultima_falha": g["dt_parada"].max(),
                "referencia": referencia,
            }
        )

    return pd.DataFrame(resultados).sort_values(
        ["prob_parar_30d", "downtime_30d_esperado_h"], ascending=False
    )


def consolidar_visoes(df: pd.DataFrame, inicio: pd.Timestamp, fim: pd.Timestamp) -> dict[str, pd.DataFrame]:
    periodo = df[(df["dt_parada"] >= inicio) & (df["dt_parada"] <= fim)].copy()
    periodo["causa_extraida"] = periodo["descricao_servico"].apply(extrair_causa_da_descricao)

    visoes: dict[str, pd.DataFrame] = {}
    visoes["pareto_falhas"] = (
        periodo.groupby("tipo_falha")
        .agg(falhas=("os_numero", "count"), downtime_h=("duracao_h", "sum"))
        .sort_values("falhas", ascending=False)
        .reset_index()
    )
    visoes["origem_interna_campo"] = (
        periodo.groupby("origem_os")
        .agg(falhas=("os_numero", "count"), mttr_h=("duracao_h", "mean"), downtime_h=("duracao_h", "sum"))
        .sort_values("falhas", ascending=False)
        .reset_index()
    )
    visoes["causas"] = (
        periodo.groupby("causa_extraida")
        .agg(falhas=("os_numero", "count"), downtime_h=("duracao_h", "sum"))
        .sort_values("falhas", ascending=False)
        .head(30)
        .reset_index()
    )
    visoes["mensal"] = (
        periodo.assign(mes=periodo["dt_parada"].dt.to_period("M").dt.to_timestamp())
        .groupby("mes")
        .agg(falhas=("os_numero", "count"), downtime_h=("duracao_h", "sum"), mttr_h=("duracao_h", "mean"))
        .reset_index()
        .sort_values("mes")
    )
    return visoes


def gerar_relatorio(input_excel: Path, pasta_saida: Path) -> None:
    pasta_saida.mkdir(parents=True, exist_ok=True)
    df = carregar_dados(input_excel)

    referencia = df["dt_parada"].max()
    j30 = JanelaAnalise(nome="30_dias", dias=30)
    j365 = JanelaAnalise(nome="12_meses", dias=365)

    kpi_30 = montar_kpis(df, j30.dias, referencia)
    kpi_12m = montar_kpis(df, j365.dias, referencia)

    inicio_12m = referencia - pd.Timedelta(days=365)
    df_12m = df[(df["dt_parada"] >= inicio_12m) & (df["dt_parada"] <= referencia)].copy()
    sim_30d = simular_monte_carlo(df_12m, referencia=referencia)
    visoes = consolidar_visoes(df, inicio_12m, referencia)

    resumo = pd.DataFrame(
        [
            {"metrica": "data_referencia", "valor": str(referencia)},
            {"metrica": "total_os_base", "valor": int(len(df))},
            {"metrica": "total_equipamentos_base", "valor": int(df["equipamento_id"].nunique())},
            {"metrica": "os_12m", "valor": int(len(df_12m))},
            {
                "metrica": "downtime_12m_h",
                "valor": float(df_12m["duracao_h"].sum()),
            },
        ]
    )

    saida_excel = pasta_saida / "resultado_pcm.xlsx"
    with pd.ExcelWriter(saida_excel, engine="openpyxl") as writer:
        resumo.to_excel(writer, index=False, sheet_name="resumo")
        kpi_30.to_excel(writer, index=False, sheet_name="kpi_30_dias")
        kpi_12m.to_excel(writer, index=False, sheet_name="kpi_12_meses")
        sim_30d.to_excel(writer, index=False, sheet_name="sim_monte_carlo_30d")
        for nome, tabela in visoes.items():
            tabela.to_excel(writer, index=False, sheet_name=nome[:31])

    # CSVs para uso em Power BI/Excel.
    kpi_30.to_csv(pasta_saida / "kpi_30_dias.csv", index=False, encoding="utf-8-sig")
    kpi_12m.to_csv(pasta_saida / "kpi_12_meses.csv", index=False, encoding="utf-8-sig")
    sim_30d.to_csv(pasta_saida / "sim_monte_carlo_30d.csv", index=False, encoding="utf-8-sig")

    print(f"Relatorio gerado com sucesso em: {saida_excel}")
    print(f"Base utilizada: {input_excel}")
    print(f"Data de referencia automatica: {referencia}")


def encontrar_arquivo_excel(pasta: Path) -> Optional[Path]:
    candidatos = list(pasta.glob("*.xlsx")) + list(pasta.glob("*.xls"))
    if not candidatos:
        return None
    # Prioriza arquivo com "paramet" no nome.
    candidatos.sort(key=lambda p: ("paramet" not in p.name.lower(), p.name.lower()))
    return candidatos[0]


if __name__ == "__main__":
    pasta_projeto = Path(__file__).resolve().parent
    arquivo_excel = encontrar_arquivo_excel(pasta_projeto)
    if arquivo_excel is None:
        raise FileNotFoundError("Nenhum arquivo Excel encontrado na pasta do projeto.")
    gerar_relatorio(arquivo_excel, pasta_projeto / "saida_pcm")
