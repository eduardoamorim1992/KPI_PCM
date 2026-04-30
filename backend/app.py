"""
API REST do Sistema PCM.
"""

from functools import lru_cache
import logging
import pandas as pd

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from analytics.kpis import calcular_disponibilidade_frota, calcular_kpis_equipamento, calcular_kpis_grupo
from analytics.monte_carlo import calcular_r_quadrado_weibull, extrair_intervalos_falha, simular_frota_completa, simular_monte_carlo
from analytics.ranking import gerar_ranking_criticos
from analytics.reliability import (
    calcular_confiabilidade_atual,
    calcular_curva_banheira_grupo,
    calcular_curva_confiabilidade,
    pontos_papel_weibull,
)
from analytics.trends import (
    backlog_aging,
    composicao_origem_por_grupo,
    disponibilidade_heatmap_semanas,
    evolucao_mttr_mensal,
    falhas_stack_por_mes,
    mtbf_mttr_por_grupo,
    ranking_criticidade_abc,
    ranking_falhas_por_equipo,
)
from data.loader import carregar_dados

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")

app = FastAPI(
    title="Sistema PCM - Gestao de Manutencao de Frotas",
    description="API para analise de manutencao, confiabilidade e simulacao de falhas",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@lru_cache(maxsize=1)
def get_dados():
    return carregar_dados()


@app.get("/api/dashboard/resumo")
def dashboard_resumo(
    grupo: str = Query(None),
    unidade: str = Query(None),
    frota: int = Query(None, description="Codigo da frota/equipamento"),
    modelo: str = Query(None),
    dt_inicio: str = Query(None, description="YYYY-MM-DD"),
    dt_fim: str = Query(None, description="YYYY-MM-DD"),
    tipo_falha: str = Query(None, description="Filtro por tipo de falha (DE_MOTENTR)"),
):
    df = get_dados()
    if grupo:
        df = df[df["grupo_equipamento"] == grupo.upper()]
    if unidade:
        df = df[df["unidade"] == unidade.upper()]
    if frota is not None:
        df = df[df["cod_equipamento"] == frota]
    if modelo:
        df = df[df["modelo"] == modelo.upper()]

    if dt_inicio:
        try:
            di = pd.to_datetime(dt_inicio)
            df = df[df["dt_entrada"] >= di]
        except Exception:
            raise HTTPException(400, "dt_inicio inválido (use YYYY-MM-DD)")
    if dt_fim:
        try:
            dfim = pd.to_datetime(dt_fim) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
            df = df[df["dt_entrada"] <= dfim]
        except Exception:
            raise HTTPException(400, "dt_fim inválido (use YYYY-MM-DD)")
    if tipo_falha:
        df = df[df["tipo_falha"] == tipo_falha.upper()]

    if len(df) == 0:
        raise HTTPException(404, "Nenhum dado encontrado para os filtros")

    periodo_dias = max((df["dt_entrada"].max() - df["dt_entrada"].min()).days, 1)
    periodo_horas = periodo_dias * 24

    df = df.copy()
    df["_mes"] = df["dt_entrada"].dt.to_period("M").astype(str)
    meses_ord = sorted(df["_mes"].dropna().unique())

    # Série mensal por tipo de falha (coluna I / DE_MOTENTR)
    # Mantém as principais falhas explícitas e agrega o resto em OUTRAS.
    falhas_vc = df[df["is_falha_real"]]["tipo_falha"].value_counts()
    top_falhas = falhas_vc.head(6).index.tolist()
    preferidas = [t for t in ["FALHA MECANICA", "DESGASTE NATURAL", "FALHA EM PNEUS", "FALHA ELETRICA"] if t in falhas_vc.index]
    # Garantir que as preferidas entrem, sem duplicar
    tipos_series = []
    for t in preferidas + top_falhas:
        if t not in tipos_series:
            tipos_series.append(t)
    tipos_series = tipos_series[:6]

    falhas_mensal = []
    for mes in meses_ord:
        sub = df[(df["_mes"] == mes) & (df["is_falha_real"])]
        linha = {"mes": mes}
        soma = 0
        for t in tipos_series:
            v = int((sub["tipo_falha"] == t).sum())
            linha[t] = v
            soma += v
        linha["OUTRAS"] = int(len(sub) - soma)
        falhas_mensal.append(linha)
    por_mes_tot = df.groupby("_mes")["num_os"].count().to_dict()
    variacao_mom_pct = None
    if len(meses_ord) >= 2:
        u, p = meses_ord[-1], meses_ord[-2]
        if por_mes_tot.get(p, 0):
            variacao_mom_pct = round((por_mes_tot.get(u, 0) - por_mes_tot.get(p, 0)) / por_mes_tot[p] * 100, 1)

    em_manutencao_agora = int(df[df["dt_saida"].isna()]["cod_equipamento"].nunique())
    if "status_os" in df.columns:
        os_abertas_periodo = int(len(df[df["status_os"] != "E"]))
        os_encerradas_periodo = int(len(df[df["status_os"] == "E"]))
    else:
        os_abertas_periodo = int(len(df[df["dt_saida"].isna()]))
        os_encerradas_periodo = int(len(df[df["dt_saida"].notna()]))

    dm_rows = calcular_disponibilidade_frota(df, periodo_horas).fillna(0)
    dm_medio = float(dm_rows["disponibilidade_pct"].mean()) if len(dm_rows) else 0.0

    return {
        "periodo": {"inicio": df["dt_entrada"].min().isoformat(), "fim": df["dt_entrada"].max().isoformat(), "dias": periodo_dias},
        "totais": {
            "total_os": int(len(df)),
            "total_equipamentos": int(df["cod_equipamento"].nunique()),
            "total_horas_parado": round(float(df["horas_parado"].sum()), 1),
            "total_falhas_reais": int(df[df["is_falha_real"]]["num_os"].count()),
        },
        "kpis": {
            "mttr_medio_horas": round(float(df["horas_parado"].mean()), 2),
            "pct_corretiva": round(float(len(df[df["tipo_manutencao"] == "CORRETIVA"]) / len(df) * 100), 1),
            "pct_programada": round(float(len(df[df["tipo_manutencao"] == "PROGRAMADA"]) / len(df) * 100), 1),
            "dm_frota_media_pct": round(dm_medio, 2),
            "variacao_os_mom_pct": variacao_mom_pct,
            "equipamentos_em_manutencao": em_manutencao_agora,
            "os_abertas_periodo": os_abertas_periodo,
            "os_encerradas_periodo": os_encerradas_periodo,
        },
        "disponibilidade_por_grupo": dm_rows.to_dict("records"),
        "os_mensal_por_falha": {"series": falhas_mensal, "tipos": tipos_series},
        "falhas_por_tipo": df[df["is_falha_real"]]["tipo_falha"].value_counts().to_dict(),
        "falhas_por_grupo": df[df["is_falha_real"]]["grupo_equipamento"].value_counts().to_dict(),
        "os_por_mes": df.groupby(df["dt_entrada"].dt.to_period("M").astype(str))["num_os"].count().to_dict(),
    }


@app.get("/api/dashboard/opcoes-filtros")
def opcoes_filtros_dashboard(grupo: str = Query(None), unidade: str = Query(None), frota: int = Query(None)):
    """
    Opcoes de filtros cascata para o Dashboard:
    - grupo -> frotas/unidades
    - (grupo, unidade) -> modelos
    - (grupo, unidade, modelo) é aplicado no /resumo
    """
    df_all = get_dados()
    grupos = sorted(df_all["grupo_equipamento"].dropna().unique().tolist())

    df = df_all
    if grupo:
        df = df[df["grupo_equipamento"] == grupo.upper()]
    if unidade:
        df = df[df["unidade"] == unidade.upper()]
    if frota is not None:
        df = df[df["cod_equipamento"] == frota]

    frotas = (
        df[["cod_equipamento", "modelo"]]
        .dropna(subset=["cod_equipamento"])
        .drop_duplicates()
        .sort_values(["cod_equipamento", "modelo"])
        .to_dict("records")
    )
    modelos = sorted(df["modelo"].dropna().unique().tolist())
    tipos_falha = (
        sorted(df[df["is_falha_real"]]["tipo_falha"].dropna().unique().tolist())
        if "is_falha_real" in df.columns
        else []
    )

    return {
        "grupos": grupos,
        "frotas": frotas,
        "modelos": modelos,
        "tipos_falha": tipos_falha,
    }


@app.get("/api/dashboard/ranking-criticos")
def ranking_criticos(grupo: str = Query(None), top_n: int = Query(20, ge=5, le=50)):
    df = get_dados()
    if grupo:
        df = df[df["grupo_equipamento"] == grupo.upper()]
    return gerar_ranking_criticos(df, top_n=top_n)


@app.get("/api/equipamentos/{cod_equipamento}/kpis")
def kpis_equipamento(cod_equipamento: int):
    df_ativo = get_dados()[lambda d: d["cod_equipamento"] == cod_equipamento]
    if len(df_ativo) == 0:
        raise HTTPException(404, f"Equipamento {cod_equipamento} nao encontrado")
    return vars(calcular_kpis_equipamento(df_ativo))


@app.get("/api/equipamentos/{cod_equipamento}/historico")
def historico_equipamento(cod_equipamento: int):
    df_ativo = get_dados()[lambda d: d["cod_equipamento"] == cod_equipamento].sort_values("dt_entrada")
    if len(df_ativo) == 0:
        raise HTTPException(404, f"Equipamento {cod_equipamento} nao encontrado")
    cols = [
        "num_os",
        "dt_entrada",
        "dt_saida",
        "horas_parado",
        "tipo_falha",
        "tipo_manutencao",
        "descricao_servico",
        "acumulado_km_hr",
        "unidade_medida",
    ]
    return df_ativo[cols].to_dict("records")


@app.get("/api/equipamentos/{cod_equipamento}/uso-atual")
def uso_atual_equipamento(cod_equipamento: int):
    """Retorna sugestão de uso atual desde última OS para alimentar Monte Carlo."""
    df_ativo = get_dados()[lambda d: d["cod_equipamento"] == cod_equipamento].sort_values("dt_entrada")
    if len(df_ativo) == 0:
        raise HTTPException(404, f"Equipamento {cod_equipamento} nao encontrado")
    un = str(df_ativo["unidade_medida"].iloc[-1]) if "unidade_medida" in df_ativo.columns else "HM"
    if un == "HR":
        un = "HM"
    uso = float(df_ativo["km_hr_percorrido"].dropna().iloc[-1]) if df_ativo["km_hr_percorrido"].notna().any() else 0.0
    return {
        "cod_equipamento": int(cod_equipamento),
        "unidade_medida": un,
        "uso_atual_sugerido": round(uso, 1),
        "data_referencia": df_ativo["dt_entrada"].iloc[-1].isoformat() if "dt_entrada" in df_ativo.columns else None,
    }


@app.get("/api/equipamentos/{cod_equipamento}/confiabilidade")
def confiabilidade_equipamento(cod_equipamento: int):
    df_ativo = get_dados()[lambda d: d["cod_equipamento"] == cod_equipamento]
    if len(df_ativo) == 0:
        raise HTTPException(404, f"Equipamento {cod_equipamento} nao encontrado")
    try:
        dist = extrair_intervalos_falha(df_ativo)
        t_atual = float(df_ativo["km_hr_percorrido"].dropna().tail(1).iloc[0]) if df_ativo["km_hr_percorrido"].notna().any() else 0.0
        curva = calcular_curva_confiabilidade(dist.beta, dist.eta, t_atual=t_atual)
        papel_obs, papel_linha = pontos_papel_weibull(dist.intervalos_reais, dist.beta, dist.eta)
        return {
            "parametros": {"beta": dist.beta, "eta": dist.eta, "r_quadrado": round(calcular_r_quadrado_weibull(dist), 3)},
            "curva": curva._asdict(),
            "banheira": {"t": curva.t, "h_t": curva.h_t},
            "papel_weibull": {"observados": papel_obs, "ajuste": papel_linha},
            "situacao_atual": {
                "t_atual": t_atual,
                "confiabilidade_pct": round(calcular_confiabilidade_atual(dist.beta, dist.eta, t_atual) * 100, 1),
                "n_observacoes": dist.n_observacoes,
            },
        }
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/simulacao/monte-carlo/{cod_equipamento}")
def simular_equipamento(
    cod_equipamento: int,
    horimetro_atual: float = Query(0, description="Uso atual desde ultima falha"),
    n_simulacoes: int = Query(10000, ge=1000, le=100000),
    horizonte_horas: float = Query(2160),
):
    df_ativo = get_dados()[lambda d: d["cod_equipamento"] == cod_equipamento]
    if len(df_ativo) == 0:
        raise HTTPException(404, f"Equipamento {cod_equipamento} nao encontrado")
    try:
        dist = extrair_intervalos_falha(df_ativo)
        unidade_medida = str(df_ativo["unidade_medida"].iloc[0]) if "unidade_medida" in df_ativo.columns else "HM"
        resultado = simular_monte_carlo(
            dist,
            horimetro_atual,
            unidade_medida=unidade_medida,
            n_simulacoes=n_simulacoes,
            horizonte_horas=horizonte_horas,
        )
        resultado.cod_equipamento = cod_equipamento
        resultado.grupo = str(df_ativo["grupo_equipamento"].iloc[0])
        resultado.modelo = str(df_ativo["modelo"].iloc[0])
        resultado.unidade_medida = unidade_medida
        kpi = calcular_kpis_equipamento(df_ativo)

        alertas = []
        if kpi.disponibilidade_pct < 70:
            alertas.append(
                {
                    "id": "DM_CRITICO",
                    "nivel": "CRITICO",
                    "mensagem": "DM abaixo de 70% — equipamento em estado crítico",
                    "acao": "Retirar de operação para revisão completa",
                }
            )
        if kpi.mttr_horas > 48:
            alertas.append(
                {
                    "id": "MTTR_ALTO",
                    "nivel": "ALTO",
                    "mensagem": "MTTR > 48h — reparo acima do aceitável",
                    "acao": "Revisar logística de peças e mão de obra",
                }
            )
        if kpi.taxa_falhas_mes > 10:
            alertas.append(
                {
                    "id": "FALHAS_FREQUENTES",
                    "nivel": "ALTO",
                    "mensagem": "Mais de 10 falhas por mês — equipamento instável",
                    "acao": "Análise de causa raiz urgente",
                }
            )
        prob_curto = resultado.probs_por_horizonte_uso[0] if resultado.probs_por_horizonte_uso else resultado.prob_falha_30d
        if prob_curto > 70:
            alertas.append(
                {
                    "id": "PROB_FALHA_ALTA",
                    "nivel": "ALTO",
                    "mensagem": "Monte Carlo: >70% de chance de falha no curto horizonte de uso",
                    "acao": "Programar preventiva imediata",
                }
            )

        return {
            **vars(resultado),
            "aviso_simulacao": (
                "Uso atual informado está muito acima do histórico típico; "
                "resultado tende a risco ~100% e tempos residuais próximos de zero."
                if (resultado.probs_por_horizonte_uso and resultado.probs_por_horizonte_uso[0] >= 99.0)
                else None
            ),
            "n_observacoes": dist.n_observacoes,
            "ks_pvalue": dist.ks_pvalue,
            "kpis_contexto": {
                "mttr_horas": kpi.mttr_horas,
                "mtbf_horas": kpi.mtbf_horas,
                "disponibilidade_pct": kpi.disponibilidade_pct,
                "taxa_falhas_mes": kpi.taxa_falhas_mes,
            },
            "alertas": alertas,
        }
    except ValueError as exc:
        raise HTTPException(400, f"Historico insuficiente: {exc}") from exc


@app.get("/api/simulacao/frota")
def simular_frota(grupo: str = Query(None), n_simulacoes: int = Query(10000, ge=1000, le=50000)):
    grupos = [grupo.upper()] if grupo else None
    out = simular_frota_completa(get_dados(), grupos=grupos, n_simulacoes=n_simulacoes)
    if out.empty:
        raise HTTPException(400, "Dados insuficientes para simulacao")
    return out.fillna(0).to_dict("records")


@app.get("/api/grupos/{grupo}/analise")
def analise_grupo(grupo: str):
    df = get_dados()
    df_grupo = df[df["grupo_equipamento"] == grupo.upper()]
    if len(df_grupo) == 0:
        raise HTTPException(404, f"Grupo '{grupo}' nao encontrado")
    return {
        "kpis": calcular_kpis_grupo(df, grupo.upper()),
        "curva_banheira": calcular_curva_banheira_grupo(df_grupo),
        "falhas_por_tipo": df_grupo[df_grupo["is_falha_real"]]["tipo_falha"].value_counts().to_dict(),
        "evolucao_mensal": df_grupo.groupby(df_grupo["dt_entrada"].dt.to_period("M").astype(str))["num_os"].count().to_dict(),
    }


@app.get("/api/grupos")
def listar_grupos():
    grupos = (
        get_dados()
        .groupby("grupo_equipamento")
        .agg(total_os=("num_os", "count"), equipamentos=("cod_equipamento", "nunique"), horas_parado=("horas_parado", "sum"))
        .reset_index()
    )
    return grupos.fillna(0).to_dict("records")


@app.get("/api/filtros/equipamentos")
def listar_equipamentos(grupo: str = Query(None)):
    df = get_dados()
    if grupo:
        df = df[df["grupo_equipamento"] == grupo.upper()]
    equip = (
        df.groupby(["cod_equipamento", "modelo", "marca", "grupo_equipamento", "ano_fabricacao", "unidade_medida"])
        .agg(total_os=("num_os", "count"), ultima_os=("dt_entrada", "max"))
        .reset_index()
    )
    return equip.fillna(0).to_dict("records")


@app.get("/api/analitico/overview")
def analitico_overview(grupo: str = Query(None), unidade: str = Query(None), frota: int = Query(None)):
    """Dados agregados para gráficos do painel analítico (MTBF/MTTR, tendências e heatmap)."""
    df = get_dados().copy()
    if grupo:
        df = df[df["grupo_equipamento"] == grupo.upper()]
    if unidade:
        df = df[df["unidade"] == unidade.upper()]
    if frota is not None:
        df = df[df["cod_equipamento"] == frota]
    if len(df) == 0:
        raise HTTPException(404, "Nenhum dado encontrado para os filtros")
    return {
        "mtbf_mttr_por_grupo": mtbf_mttr_por_grupo(df),
        "evolucao_mttr_mensal": evolucao_mttr_mensal(df),
        "falhas_stack_mes": falhas_stack_por_mes(df),
        "composicao_origem": composicao_origem_por_grupo(df),
        "heatmap_dm": disponibilidade_heatmap_semanas(df),
        "top_falhas_equip": ranking_falhas_por_equipo(df, 10),
        "criticidade_abc": ranking_criticidade_abc(df, 20),
        "backlog_aging": backlog_aging(df),
        "filtros": {"grupo": grupo, "unidade": unidade},
    }


@app.get("/health")
@app.get("/api/health")
def health_check():
    df = get_dados()
    return {
        "status": "ok",
        "total_registros": int(len(df)),
        "periodo_inicio": df["dt_entrada"].min().isoformat(),
        "periodo_fim": df["dt_entrada"].max().isoformat(),
    }
