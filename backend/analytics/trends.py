"""Séries temporais e agregações para o painel analítico."""

import pandas as pd

from analytics.kpis import calcular_kpis_equipamento


def mtbf_mttr_por_grupo(df: pd.DataFrame) -> list[dict]:
    """Por grupo: médias de MTBF/MTTR agregadas por equipamento."""
    out = []
    for grupo in sorted(df["grupo_equipamento"].dropna().unique()):
        g = df[df["grupo_equipamento"] == grupo]
        mttrs = []
        mtbfs = []
        for cod in g["cod_equipamento"].dropna().unique():
            sub = g[g["cod_equipamento"] == cod]
            try:
                k = calcular_kpis_equipamento(sub)
                if k.os_falhas_reais > 0:
                    mttrs.append(k.mttr_horas)
                if k.mtbf_horas > 0:
                    mtbfs.append(k.mtbf_horas)
            except Exception:
                continue
        out.append(
            {
                "grupo": str(grupo),
                "mttr_medio": round(float(pd.Series(mttrs).mean()), 2) if mttrs else 0.0,
                "mtbf_medio": round(float(pd.Series(mtbfs).mean()), 2) if mtbfs else 0.0,
                "n_equipamentos": int(g["cod_equipamento"].nunique()),
            }
        )
    return out


def evolucao_mttr_mensal(df: pd.DataFrame) -> list[dict]:
    """MTTR médio (falhas reais) por mês."""
    fal = df[df["is_falha_real"]].copy()
    if fal.empty:
        return []
    fal["_mes"] = fal["dt_entrada"].dt.to_period("M").astype(str)
    rows = []
    for mes in sorted(fal["_mes"].unique()):
        sub = fal[fal["_mes"] == mes]
        m = float(sub["horas_parado"].fillna(0).mean()) if len(sub) else 0.0
        rows.append({"mes": mes, "mttr_medio": round(m, 2), "qtd_falhas": int(len(sub))})
    return rows


def falhas_stack_por_mes(df: pd.DataFrame) -> dict:
    """Histórico mensal por tipo de falha (falhas reais)."""
    fal = df[df["is_falha_real"]].copy()
    if fal.empty:
        return {"meses_linhas": [], "tipos": []}
    fal["_mes"] = fal["dt_entrada"].dt.to_period("M").astype(str)
    tipos = sorted(fal["tipo_falha"].astype(str).unique())
    meses = sorted(fal["_mes"].unique())
    meses_linhas = []
    for mes in meses:
        linha = {"mes": mes}
        sub = fal[fal["_mes"] == mes]
        for t in tipos:
            linha[t] = int((sub["tipo_falha"].astype(str) == t).sum())
        meses_linhas.append(linha)
    return {"meses_linhas": meses_linhas, "tipos": tipos}


def composicao_origem_por_grupo(df: pd.DataFrame) -> list[dict]:
    linhas = []
    for grupo in sorted(df["grupo_equipamento"].dropna().unique()):
        g = df[df["grupo_equipamento"] == grupo]
        n = len(g)
        if n == 0:
            continue
        linhas.append(
            {
                "grupo": str(grupo),
                "pct_corretiva": round(len(g[g["tipo_manutencao"] == "CORRETIVA"]) / n * 100, 1),
                "pct_programada": round(len(g[g["tipo_manutencao"] == "PROGRAMADA"]) / n * 100, 1),
                "pct_terceirizada": round(len(g[g["tipo_manutencao"] == "TERCEIRIZADA"]) / n * 100, 1),
                "pct_outros": round(len(g[~g["tipo_manutencao"].isin(["CORRETIVA", "PROGRAMADA", "TERCEIRIZADA"])]) / n * 100, 1),
            }
        )
    return linhas


def disponibilidade_heatmap_semanas(df: pd.DataFrame, horas_semana: float = 168.0) -> list[dict]:
    """
    DM semanal simplificada por grupo: capacidade grupal = n_equip × 168h,
    menos horas_parado da semana sobre total atribuídas ao mesmo grupo (proxy).
    """
    resultado = []
    for grupo in sorted(df["grupo_equipamento"].dropna().unique()):
        dg = df[df["grupo_equipamento"] == grupo].copy()
        n_eq = int(dg["cod_equipamento"].nunique())
        if n_eq == 0:
            continue
        dg["_wk"] = (
            dg["dt_entrada"].dt.isocalendar().year.astype(str)
            + "-W"
            + dg["dt_entrada"].dt.isocalendar().week.astype(str).str.zfill(2)
        )
        for _w, grp in dg.groupby("_wk"):
            hp = float(grp["horas_parado"].fillna(0).sum())
            cap_hours = max(n_eq * horas_semana, 1.0)
            dm_approx = max(0.0, min(100.0, (cap_hours - min(hp, cap_hours)) / cap_hours * 100))
            resultado.append({"grupo": str(grupo), "semana": str(_w), "dm_approx": round(dm_approx, 1)})
    resultado.sort(key=lambda x: x["semana"])
    return resultado[-60:]


def ranking_falhas_por_equipo(df: pd.DataFrame, top_n: int = 10) -> list[dict]:
    fal = df[df["is_falha_real"]].copy()
    cnt = fal.groupby(["cod_equipamento", "grupo_equipamento", "modelo"]).size().sort_values(ascending=False).head(top_n)
    out = []
    for (cod, grupo, modelo), qtd in cnt.items():
        out.append(
            {
                "cod_equipamento": int(cod),
                "frota": str(int(cod)),
                "grupo": str(grupo),
                "modelo": str(modelo),
                "n_falhas": int(qtd),
            }
        )
    return out


def ranking_criticidade_abc(df: pd.DataFrame, top_n: int = 20) -> list[dict]:
    """
    Matriz ABC de criticidade baseada em:
    - impacto (horas paradas acumuladas),
    - frequencia (falhas reais),
    - mttr (tempo medio de reparo).
    """
    base = (
        df.groupby(["cod_equipamento", "grupo_equipamento", "modelo"], dropna=True)
        .agg(
            total_os=("num_os", "count"),
            falhas_reais=("is_falha_real", "sum"),
            impacto_horas=("horas_parado", "sum"),
        )
        .reset_index()
    )
    if base.empty:
        return []

    falhas = df[df["is_falha_real"]].copy()
    mttr = (
        falhas.groupby("cod_equipamento", dropna=True)["horas_parado"]
        .mean()
        .rename("mttr_horas")
        .reset_index()
    )
    base = base.merge(mttr, on="cod_equipamento", how="left")
    base["mttr_horas"] = base["mttr_horas"].fillna(0.0)

    def _norm(s: pd.Series) -> pd.Series:
        vmax = float(s.max()) if len(s) else 0.0
        return (s.astype(float) / vmax * 100.0) if vmax > 0 else pd.Series([0.0] * len(s), index=s.index)

    base["impacto_score"] = _norm(base["impacto_horas"])
    base["frequencia_score"] = _norm(base["falhas_reais"])
    base["mttr_score"] = _norm(base["mttr_horas"])
    base["score_criticidade"] = (
        base["impacto_score"] * 0.4 + base["frequencia_score"] * 0.35 + base["mttr_score"] * 0.25
    ).round(1)

    base = base.sort_values("score_criticidade", ascending=False).reset_index(drop=True)
    total_score = float(base["score_criticidade"].sum())
    if total_score <= 0:
        base["classe_abc"] = "C"
    else:
        acumulado = base["score_criticidade"].cumsum() / total_score * 100.0
        base["classe_abc"] = acumulado.map(lambda x: "A" if x <= 80 else ("B" if x <= 95 else "C"))

    out = []
    for _, r in base.head(top_n).iterrows():
        out.append(
            {
                "cod_equipamento": int(r["cod_equipamento"]),
                "frota": str(int(r["cod_equipamento"])),
                "grupo": str(r["grupo_equipamento"]),
                "modelo": str(r["modelo"]),
                "total_os": int(r["total_os"]),
                "falhas_reais": int(r["falhas_reais"]),
                "impacto_horas": round(float(r["impacto_horas"]), 1),
                "mttr_horas": round(float(r["mttr_horas"]), 1),
                "score_criticidade": float(r["score_criticidade"]),
                "classe_abc": str(r["classe_abc"]),
            }
        )
    return out


def backlog_aging(df: pd.DataFrame) -> dict:
    """
    Backlog com envelhecimento por status aberto.
    Quando nao houver data de abertura dedicada, usa dt_entrada como proxy.
    """
    st = df["status_os"].fillna("").astype(str)
    mask_aberta = st.str.contains("ABER|PEND|EXEC|ANDAM", regex=True)
    ab = df[mask_aberta].copy()
    if ab.empty:
        return {"kpis": {"total_abertas": 0, "idade_media_dias": 0.0}, "faixas": []}

    now = pd.Timestamp.now().normalize()
    ab["idade_dias"] = (now - ab["dt_entrada"].dt.normalize()).dt.days.clip(lower=0)

    def _faixa(v: float) -> str:
        if v <= 7:
            return "0-7"
        if v <= 15:
            return "8-15"
        if v <= 30:
            return "16-30"
        if v <= 60:
            return "31-60"
        return ">60"

    ab["faixa"] = ab["idade_dias"].map(_faixa)
    ordem = ["0-7", "8-15", "16-30", "31-60", ">60"]
    grp = ab.groupby("faixa")["num_os"].count()
    faixas = [{"faixa": f, "qtd_os": int(grp.get(f, 0))} for f in ordem]

    kpis = {
        "total_abertas": int(len(ab)),
        "idade_media_dias": round(float(ab["idade_dias"].mean()), 1),
        "idade_p90_dias": round(float(ab["idade_dias"].quantile(0.9)), 1),
        "pct_maior_30d": round(float((ab["idade_dias"] > 30).mean() * 100.0), 1),
    }
    return {"kpis": kpis, "faixas": faixas}
