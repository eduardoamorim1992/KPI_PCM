from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from simulador_pcm import carregar_dados, encontrar_arquivo_excel, extrair_causa_da_descricao

try:
    from scipy.stats import weibull_min

    SCIPY_OK = True
except Exception:
    SCIPY_OK = False


def parse_previsao_horas(texto: object) -> Optional[float]:
    if not isinstance(texto, str):
        return None
    padrao = re.search(r"PREVIS[ÃA]O\s*[:;]?\s*([\d.,]+)\s*H", texto.upper())
    if not padrao:
        return None
    valor = padrao.group(1).replace(".", "").replace(",", ".")
    try:
        return float(valor)
    except ValueError:
        return None


def normalizar_codigo_texto(valor: object) -> str:
    if pd.isna(valor):
        return "Não informado"
    texto = str(valor).strip()
    if texto == "" or texto.lower() == "nan":
        return "Não informado"
    if texto.endswith(".0"):
        texto = texto[:-2]
    return texto


@st.cache_data(show_spinner=False)
def carregar_base(path_excel: str, cache_version: str = "v4") -> tuple[pd.DataFrame, pd.DataFrame]:
    raw = pd.read_excel(path_excel)
    df = carregar_dados(Path(path_excel))
    if "frota" not in df.columns:
        # Compatibilidade com cache antigo ou versoes anteriores do script base.
        origem_frota = df["equipamento_id"] if "equipamento_id" in df.columns else pd.Series(dtype="object")
        df["frota"] = origem_frota.apply(normalizar_codigo_texto)
    else:
        df["frota"] = df["frota"].apply(normalizar_codigo_texto)
    if "tipo_deslocamento" not in df.columns and "CD_UNIMED" in raw.columns:
        df["tipo_deslocamento"] = raw["CD_UNIMED"].astype(str).str.strip().replace({"nan": "Não informado", "": "Não informado"})
    if "tipo_deslocamento" in df.columns:
        df["tipo_deslocamento"] = df["tipo_deslocamento"].astype(str).str.strip().replace({"nan": "Não informado", "": "Não informado"})
    df["causa_extraida"] = df["descricao_servico"].apply(extrair_causa_da_descricao)
    df["previsao_h"] = df["descricao_servico"].apply(parse_previsao_horas)
    return raw, df


def filtrar_periodo(df: pd.DataFrame, dias: int, referencia: pd.Timestamp) -> pd.DataFrame:
    inicio = referencia - pd.Timedelta(days=dias)
    return df[(df["dt_parada"] >= inicio) & (df["dt_parada"] <= referencia)].copy()


def kpis_por_equipamento(df: pd.DataFrame, dias: int) -> pd.DataFrame:
    ordenado = df.sort_values(["equipamento_id", "dt_parada"]).copy()
    ordenado["delta_h"] = (
        ordenado.groupby("equipamento_id")["dt_parada"].diff().dt.total_seconds() / 3600.0
    )
    ordenado["delta_uso"] = (
        ordenado.groupby("equipamento_id")["km_hr_acumulado"].diff().abs()
    )
    ordenado.loc[ordenado["delta_uso"] <= 0, "delta_uso"] = np.nan
    horas_periodo = dias * 24
    agg = (
        ordenado.groupby(["equipamento_id", "frota", "unidade", "modelo", "marca", "tipo_equipamento"])
        .agg(
            falhas=("os_numero", "count"),
            downtime_h=("duracao_h", "sum"),
            mttr_h=("duracao_h", "mean"),
            mtbf_intervalo_h=("delta_h", "mean"),
            mtbf_intervalo_uso=("delta_uso", "mean"),
            uso_min=("km_hr_acumulado", "min"),
            uso_max=("km_hr_acumulado", "max"),
            ultima_falha=("dt_parada", "max"),
            tipo_falha_top=("tipo_falha", lambda s: s.value_counts().index[0] if len(s) else "Não informado"),
            tipo_deslocamento=("tipo_deslocamento", lambda s: s.value_counts().index[0] if len(s) else "Não informado"),
        )
        .reset_index()
    )
    agg["mtbf_h"] = agg["mtbf_intervalo_h"].fillna(
        (horas_periodo - agg["downtime_h"]).clip(lower=0) / agg["falhas"].clip(lower=1)
    )
    agg["lambda_h"] = 1 / agg["mtbf_h"].replace(0, np.nan)
    agg["disponibilidade"] = agg["mtbf_h"] / (agg["mtbf_h"] + agg["mttr_h"]).replace(0, np.nan)
    agg["tempo_proxima_falha_h"] = agg["mtbf_h"]
    agg["falhas_esperadas_periodo"] = dias * 24 * agg["lambda_h"]
    uso_periodo = (agg["uso_max"] - agg["uso_min"]).clip(lower=0)
    mtbf_uso_fallback = uso_periodo / agg["falhas"].clip(lower=1)
    agg["mtbf_uso"] = agg["mtbf_intervalo_uso"].fillna(mtbf_uso_fallback)
    agg.loc[agg["mtbf_uso"] <= 0, "mtbf_uso"] = np.nan
    agg["lambda_uso"] = 1 / agg["mtbf_uso"]
    agg["tempo_proxima_falha_uso"] = agg["mtbf_uso"]
    return agg


def confiabilidade(mtbf_h: float, t_h: float) -> tuple[float, float]:
    if not mtbf_h or np.isnan(mtbf_h) or mtbf_h <= 0:
        return np.nan, np.nan
    lamb = 1 / mtbf_h
    r_t = math.exp(-lamb * t_h)
    f_t = 1 - r_t
    return r_t, f_t


def fit_weibull(tempos_h: np.ndarray) -> tuple[float, float]:
    tempos_h = tempos_h[np.isfinite(tempos_h)]
    tempos_h = tempos_h[tempos_h > 0]
    if len(tempos_h) < 8:
        return np.nan, np.nan
    if SCIPY_OK:
        beta, _, eta = weibull_min.fit(tempos_h, floc=0)
        return float(beta), float(eta)
    # Fallback aproximado se scipy nao estiver disponivel.
    q50 = float(np.quantile(tempos_h, 0.5))
    q90 = float(np.quantile(tempos_h, 0.9))
    beta = np.clip(np.log(np.log(10)) - np.log(np.log(2)) / np.log(q90 / max(q50, 1e-6)), 0.5, 5.0)
    eta = q50 / (np.log(2) ** (1 / beta))
    return float(beta), float(eta)


def classificar_falha_weibull(beta: float) -> str:
    if np.isnan(beta):
        return "Dados insuficientes"
    if beta < 1:
        return "Infantil (mortalidade inicial)"
    if 0.95 <= beta <= 1.2:
        return "Aleatoria (taxa quase constante)"
    return "Desgaste (envelhecimento)"


def simular_monte_carlo_equip(lambda_evento: float, duracoes_h: np.ndarray, horizonte_evento: float, n: int = 5000) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    lam = max(lambda_evento, 1e-6) * horizonte_evento
    falhas = rng.poisson(lam=lam, size=n)
    duracoes_h = duracoes_h[duracoes_h > 0]
    if len(duracoes_h) == 0:
        duracoes_h = np.array([1.0])
    downtime = np.zeros(n)
    for i, f in enumerate(falhas):
        if f > 0:
            downtime[i] = rng.choice(duracoes_h, size=f, replace=True).sum()
    return pd.DataFrame({"falhas": falhas, "downtime_h": downtime})


def sugestoes_manutencao(row: pd.Series) -> str:
    rec = []
    if row["disponibilidade"] < 0.85:
        rec.append("Priorizar preventiva semanal e revisão de causa raiz")
    if row["prob_falha_uso"] > 0.7:
        rec.append("Criar plano de contingência e check-list diário")
    if row["falhas"] >= 5:
        rec.append("Abrir análise FMEA e plano de ação estruturado")
    if row["mttr_h"] > 12:
        rec.append("Revisar recursos, ferramental e tempo de atendimento")
    return " | ".join(rec) if rec else "Manter rotina atual e monitorar tendência"


def aplicar_estilo_grafico(fig, percentual_x: bool = False, percentual_y: bool = False):
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=20, r=20, t=60, b=20),
        legend_title_text="",
    )
    fig.update_traces(marker_line_width=0)
    if percentual_x:
        fig.update_xaxes(tickformat=".0%")
    if percentual_y:
        fig.update_yaxes(tickformat=".0%")
    return fig


def secao_com_ajuda(titulo: str, ajuda: str):
    col_t, col_q = st.columns([0.94, 0.06])
    with col_t:
        st.subheader(titulo)
    with col_q:
        with st.popover("❓", use_container_width=True):
            st.markdown(ajuda)


def interpretar_cenario(
    mtbf_h: float, mttr_h: float, disponibilidade: float, oee: float, ranking: pd.DataFrame
) -> tuple[str, str, str]:
    if disponibilidade < 0.85 or oee < 0.75:
        nivel = "ALTO"
        classe = "error"
        msg = "Risco elevado de indisponibilidade. Ação imediata recomendada."
    elif disponibilidade < 0.92 or oee < 0.82:
        nivel = "MEDIO"
        classe = "warning"
        msg = "Risco moderado. Ajustar plano preventivo e monitorar ativos críticos."
    else:
        nivel = "BAIXO"
        classe = "success"
        msg = "Condição estável. Manter rotina preventiva e vigilância de tendência."

    if mttr_h > 8:
        manut = "Reduzir MTTR: revisar equipe, ferramental e logística de atendimento."
    elif mtbf_h < 24:
        manut = "Aumentar MTBF: reforçar inspeção e manutenção baseada em condição."
    else:
        manut = "Preventiva sugerida: intervalo entre 60% e 80% do MTBF por equipamento."

    top3 = ranking.head(3)["equipamento_id"].tolist() if not ranking.empty else []
    prior = ", ".join(top3) if top3 else "Sem ativos críticos no filtro atual."
    resumo = f"Semáforo: {nivel}. {msg} Priorizar ativos: {prior}"
    return classe, resumo, manut


st.set_page_config(page_title="PCM Inteligente - Confiabilidade", page_icon="🛠️", layout="wide")
st.markdown(
    """
<style>
    .stMetric {
        background: linear-gradient(135deg, rgba(56,189,248,0.10), rgba(99,102,241,0.12));
        border: 1px solid rgba(148,163,184,0.25);
        border-radius: 14px;
        padding: 10px 12px;
        box-shadow: 0 6px 18px rgba(2, 6, 23, 0.25);
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 12px;
        background: rgba(51, 65, 85, 0.25);
        border: 1px solid rgba(148,163,184,0.2);
    }
</style>
""",
    unsafe_allow_html=True,
)
st.title("🛠️ Sistema Inteligente de PCM (Planejamento e Controle da Manutenção) e Confiabilidade")
st.caption(
    "MTBF (Tempo Médio Entre Falhas), MTTR (Tempo Médio de Reparo), Weibull (modelo de comportamento de falhas), "
    "risco, Monte Carlo (simulação probabilística), custos e recomendações automáticas"
)

arquivo_upload = st.sidebar.file_uploader("Enviar base Excel", type=["xlsx", "xls"])
arquivo_padrao = encontrar_arquivo_excel(Path("."))
path_entrada = None
if arquivo_upload is not None:
    path_entrada = "base_upload_pcm.xlsx"
    with open(path_entrada, "wb") as f:
        f.write(arquivo_upload.getbuffer())
elif arquivo_padrao:
    path_entrada = str(arquivo_padrao)

if not path_entrada:
    st.error("Nenhum arquivo Excel encontrado. Coloque um .xlsx na pasta do projeto ou envie o arquivo.")
    st.stop()

raw, df = carregar_base(path_entrada, cache_version="v4")
referencia = df["dt_parada"].max()

st.sidebar.subheader("Filtros")
janela = st.sidebar.selectbox("Período de análise", ["30 dias", "12 meses"], index=1)
dias = 30 if janela == "30 dias" else 365

unidades = st.sidebar.multiselect("Unidade", sorted(df["unidade"].dropna().unique().tolist()))
base_tipo = df.copy()
if unidades:
    base_tipo = base_tipo[base_tipo["unidade"].isin(unidades)]
tipos = st.sidebar.multiselect("Tipo de equipamento", sorted(base_tipo["tipo_equipamento"].dropna().unique().tolist()))
base_modelo = base_tipo.copy()
if tipos:
    base_modelo = base_modelo[base_modelo["tipo_equipamento"].isin(tipos)]
modelos = st.sidebar.multiselect("Modelo", sorted(base_modelo["modelo"].dropna().unique().tolist()))
base_frota = base_modelo.copy()
if modelos:
    base_frota = base_frota[base_frota["modelo"].isin(modelos)]
frotas = st.sidebar.multiselect("Frota", sorted(base_frota["frota"].dropna().unique().tolist()))

t_horizonte = st.sidebar.slider("Horizonte para R(t) / F(t) (horas)", min_value=24, max_value=720, value=168, step=24)
horizonte_km = st.sidebar.number_input("Horizonte de previsão por uso (KM)", min_value=1.0, value=1000.0, step=100.0)
horizonte_hr = st.sidebar.number_input("Horizonte de previsão por uso (HR)", min_value=1.0, value=200.0, step=10.0)
qtd_simulacoes_mc = int(st.sidebar.number_input("Quantidade de simulações Monte Carlo", min_value=500, max_value=50000, value=5000, step=500))
deslocamento_mc = st.sidebar.selectbox("Deslocamento para Monte Carlo", ["Automático (equipamento)", "KM", "HR"], index=0)
etapas_anim_mc = int(
    st.sidebar.number_input(
        "Etapas da animação Monte Carlo",
        min_value=20,
        max_value=300,
        value=120,
        step=10,
    )
)
velocidade_anim_mc = st.sidebar.selectbox(
    "Velocidade da animação",
    ["Lenta", "Normal", "Rápida", "Máxima"],
    index=2,
)
prod_hora = st.sidebar.number_input("Impacto produção por hora parada (R$)", min_value=0.0, value=500.0, step=50.0)
custo_prev = st.sidebar.number_input("Custo médio preventiva (R$)", min_value=0.0, value=1500.0, step=100.0)
custo_corr = st.sidebar.number_input("Custo médio corretiva (R$)", min_value=0.0, value=4500.0, step=100.0)
perf_oee = st.sidebar.slider("Performance para OEE", 0.5, 1.0, 0.9, 0.01)
qual_oee = st.sidebar.slider("Qualidade para OEE", 0.5, 1.0, 0.98, 0.01)

base = filtrar_periodo(df, dias=dias, referencia=referencia)
if unidades:
    base = base[base["unidade"].isin(unidades)]
if tipos:
    base = base[base["tipo_equipamento"].isin(tipos)]
if modelos:
    base = base[base["modelo"].isin(modelos)]
if frotas:
    base = base[base["frota"].isin(frotas)]

if base.empty:
    st.warning("Sem dados para os filtros selecionados.")
    st.stop()

kpi = kpis_por_equipamento(base, dias=dias)
kpi["R_t"], kpi["F_t"] = zip(*kpi["mtbf_h"].map(lambda m: confiabilidade(m, t_horizonte)))
kpi["horizonte_uso"] = np.where(kpi["tipo_deslocamento"] == "KM", horizonte_km, horizonte_hr)
kpi["prob_falha_uso"] = 1 - np.exp(-(kpi["lambda_uso"].fillna(0) * kpi["horizonte_uso"]))
kpi["falhas_esperadas_uso"] = kpi["lambda_uso"].fillna(0) * kpi["horizonte_uso"]
kpi["risco_financeiro_uso"] = kpi["prob_falha_uso"] * kpi["mttr_h"] * prod_hora
kpi["intervalo_prev_uso"] = np.where(kpi["mttr_h"] > 8, kpi["mtbf_uso"] * 0.6, kpi["mtbf_uso"] * 0.8)
kpi["crit_score"] = (
    kpi["prob_falha_uso"].rank(pct=True) * 0.5
    + kpi["downtime_h"].rank(pct=True) * 0.3
    + kpi["falhas"].rank(pct=True) * 0.2
)
kpi["sugestao_plano"] = kpi.apply(sugestoes_manutencao, axis=1)
ranking_global = kpi.sort_values("crit_score", ascending=False).copy()

falhas_total = int(kpi["falhas"].sum())
mtbf_geral = float((kpi["mtbf_h"] * kpi["falhas"]).sum() / max(falhas_total, 1))
mttr_geral = float((kpi["mttr_h"] * kpi["falhas"]).sum() / max(falhas_total, 1))
disp = mtbf_geral / max(mtbf_geral + mttr_geral, 1e-6)
lambda_geral = 1 / max(mtbf_geral, 1e-6)
oee = disp * perf_oee * qual_oee
box_classe, box_resumo, box_manut = interpretar_cenario(
    mtbf_geral, mttr_geral, disp, oee, ranking_global
)

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("MTBF (Tempo Médio Entre Falhas) (h)", f"{mtbf_geral:,.1f}")
col2.metric("MTTR (Tempo Médio de Reparo) (h)", f"{mttr_geral:,.1f}")
col3.metric("Disponibilidade (tempo disponível)", f"{disp * 100:,.2f}%")
col4.metric("Taxa de falha λ (frequência de falha) (1/h)", f"{lambda_geral:,.5f}")
col5.metric("OEE (Eficiência Global do Equipamento)", f"{oee * 100:,.2f}%")

if box_classe == "error":
    st.error(box_resumo)
elif box_classe == "warning":
    st.warning(box_resumo)
else:
    st.success(box_resumo)
st.info(f"Recomendação automática de plano: {box_manut}")

aba0, aba1, aba2, aba3, aba4, aba5 = st.tabs(
    ["📘 Manual de Uso", "📊 Dashboard", "⚠️ Risco e Alertas", "📈 Confiabilidade/Weibull", "🎲 Simulações", "💰 Custos e Plano"]
)

with aba0:
    secao_com_ajuda(
        "Como usar o sistema PCM Inteligente",
        "Use esta aba para entender o fluxo de análise e o significado matemático dos indicadores.",
    )
    st.markdown(
        """
1. **Carregue os dados**: use o upload lateral ou mantenha o arquivo `parametro.xlsx` na pasta do projeto.
2. **Defina o período**: escolha 30 dias ou 12 meses para recalcular todos os indicadores.
3. **Filtre por contexto**: selecione unidade -> tipo de equipamento -> modelo -> frota (filtros em cascata).
4. **Leia os KPIs principais**: MTBF, MTTR, disponibilidade, lambda e OEE no topo da tela.
5. **Analise risco**: veja ranking crítico, alertas automáticos e probabilidade de parada.
6. **Use confiabilidade**: interprete `R(t)` e `F(t)` no horizonte em horas e a curva Weibull.
7. **Simule cenários**: compare melhor/base/pior caso e impacto na produção.
8. **Decida plano de manutenção**: use custos, backlog e recomendações automáticas da aba final.
        """
    )
    st.markdown(
        """
**Manual dos cálculos**

- **MTBF (h)** = média do tempo entre falhas por equipamento.
- **MTTR (h)** = média do tempo de reparo (`dt_retorno - dt_parada`).
- **Disponibilidade (%)** = `MTBF / (MTBF + MTTR) * 100`.
- **Taxa de falha λ (1/h)** = `1 / MTBF`.
- **Confiabilidade R(t) (%)** = `e^(-λ*t) * 100`.
- **Probabilidade de falha F(t) (%)** = `(1 - R(t)) * 100`.
- **Falhas esperadas no período** = `λ * horas do período`.
- **Probabilidade de falha no horizonte de uso (%)** = `1 - e^(-λ_uso * horizonte_uso)`.
- **Falhas esperadas no horizonte de uso** = `λ_uso * horizonte_uso`.
- **OEE (%)** = `Disponibilidade * Performance * Qualidade * 100`.
- **Intervalo preventivo ideal (h)**: regra prática em função de MTBF e MTTR.
- **Classe Weibull**:
  - `beta < 1`: falha infantil
  - `beta ~ 1`: falha aleatória
  - `beta > 1`: falha por desgaste
        """
    )
    st.markdown(
        """
**Coluna S (tipo de deslocamento)**

- A coluna `S` (campo `CD_UNIMED`) informa se o ativo é medido em:
  - `KM`: quilometragem
  - `HR`: horímetro
- Essa informação é exibida no sistema como `tipo_deslocamento` para apoiar interpretação de uso do equipamento.
        """
    )
    st.info(
        "Dica PCM: comece por unidade, depois refine por tipo, modelo e frota para priorizar os ativos mais críticos sem misturar contextos."
    )

with aba1:
    secao_com_ajuda(
        "Indicadores KPI de manutenção",
        "Visualize volume de falhas, horas paradas e indicadores técnicos por equipamento.",
    )
    c1, c2 = st.columns(2)
    pareto = (
        base.groupby("tipo_falha").agg(falhas=("os_numero", "count")).reset_index().sort_values("falhas", ascending=False).head(12)
    )
    fig_pareto = px.bar(
        pareto,
        x="tipo_falha",
        y="falhas",
        title="Pareto de falhas",
        color="falhas",
        color_continuous_scale="Blues",
        labels={"tipo_falha": "Tipo de falha", "falhas": "Quantidade"},
    )
    fig_pareto.update_layout(xaxis_title="Tipo de falha", yaxis_title="Quantidade de falhas")
    fig_pareto = aplicar_estilo_grafico(fig_pareto)
    c1.plotly_chart(fig_pareto, use_container_width=True)
    c1.caption("❓ Pareto: barras mais altas indicam os tipos de falha que mais contribuem para ocorrências.")

    mensal = (
        base.assign(mes=base["dt_parada"].dt.to_period("M").dt.to_timestamp())
        .groupby("mes")
        .agg(falhas=("os_numero", "count"), downtime_h=("duracao_h", "sum"))
        .reset_index()
    )
    fig_trend = go.Figure()
    fig_trend.add_trace(
        go.Scatter(
            x=mensal["mes"],
            y=mensal["falhas"],
            mode="lines+markers",
            name="Falhas",
            line=dict(color="#60a5fa", width=3),
            yaxis="y1",
        )
    )
    fig_trend.add_trace(
        go.Scatter(
            x=mensal["mes"],
            y=mensal["downtime_h"],
            mode="lines+markers",
            name="Tempo de parada (h)",
            line=dict(color="#f59e0b", width=3),
            yaxis="y2",
        )
    )
    fig_trend.update_layout(
        title="Tendência de falhas e paradas (eixo duplo)",
        xaxis_title="Mês",
        yaxis=dict(title="Falhas", side="left"),
        yaxis2=dict(title="Tempo de parada (h)", overlaying="y", side="right"),
    )
    fig_trend = aplicar_estilo_grafico(fig_trend)
    c2.plotly_chart(fig_trend, use_container_width=True)
    c2.caption("❓ Eixo esquerdo = número de falhas; eixo direito = horas de parada.")

    tabela_kpi = (
        kpi[["equipamento_id", "frota", "unidade", "tipo_equipamento", "tipo_deslocamento", "falhas", "mtbf_h", "mttr_h", "disponibilidade", "R_t", "F_t"]]
        .sort_values("falhas", ascending=False)
        .head(25)
        .copy()
    )
    tabela_kpi["disponibilidade"] = (tabela_kpi["disponibilidade"] * 100).map(lambda v: f"{v:,.2f}%")
    tabela_kpi["R_t"] = (tabela_kpi["R_t"] * 100).map(lambda v: f"{v:,.2f}%")
    tabela_kpi["F_t"] = (tabela_kpi["F_t"] * 100).map(lambda v: f"{v:,.2f}%")
    st.dataframe(tabela_kpi, use_container_width=True)

with aba2:
    secao_com_ajuda(
        "Ranking de equipamentos críticos e alertas automáticos",
        "A tabela prioriza ativos por score de criticidade. O gráfico cruza probabilidade de falha e MTTR.",
    )
    ranking = ranking_global.copy()
    ranking["alerta"] = np.where(ranking["prob_falha_uso"] > 0.7, "ALTO", np.where(ranking["prob_falha_uso"] > 0.4, "MEDIO", "BAIXO"))
    st.caption("Leitura rápida: X = probabilidade de falha no horizonte de uso, Y = MTTR, tamanho da bolha = impacto de parada.")
    tabela_risco = ranking[
            [
                "equipamento_id",
                "frota",
                "unidade",
                "tipo_deslocamento",
                "tipo_falha_top",
                "falhas",
                "prob_falha_uso",
                "tempo_proxima_falha_uso",
                "alerta",
                "sugestao_plano",
            ]
        ].head(30).copy()
    tabela_risco["prob_falha_uso"] = tabela_risco["prob_falha_uso"] * 100
    st.dataframe(
        tabela_risco,
        use_container_width=True,
        hide_index=True,
        column_config={
            "equipamento_id": st.column_config.TextColumn("Equipamento"),
            "frota": st.column_config.TextColumn("Frota"),
            "unidade": st.column_config.TextColumn("Unidade"),
            "tipo_deslocamento": st.column_config.TextColumn("Tipo uso"),
            "tipo_falha_top": st.column_config.TextColumn("Falha principal"),
            "falhas": st.column_config.NumberColumn("Qtd falhas", format="%d"),
            "prob_falha_uso": st.column_config.NumberColumn("Prob. falha (uso)", format="%.2f%%"),
            "tempo_proxima_falha_uso": st.column_config.NumberColumn("Prox. falha (KM/HR)", format="%.2f"),
            "alerta": st.column_config.TextColumn("Alerta"),
            "sugestao_plano": st.column_config.TextColumn("Sugestao automatica"),
        },
    )
    fig_risk = px.scatter(
        ranking.head(100),
        x="prob_falha_uso",
        y="mttr_h",
        size="downtime_h",
        color="alerta",
        hover_data=["equipamento_id", "tipo_falha_top"],
        title="Risco de falha por equipamento",
        color_discrete_map={"ALTO": "#ef4444", "MEDIO": "#f59e0b", "BAIXO": "#22c55e"},
        labels={
            "prob_falha_uso": "Probabilidade de falha",
            "mttr_h": "MTTR (h)",
            "downtime_h": "Tempo parado (h)",
            "alerta": "Alerta",
            "equipamento_id": "Equipamento",
            "tipo_falha_top": "Falha principal",
        },
    )
    fig_risk.update_xaxes(range=[0, 1], tickformat=".0%", title="Probabilidade de falha (horizonte de uso)")
    fig_risk.update_yaxes(title="MTTR (horas)")
    fig_risk.update_layout(
        legend_title_text="Nivel de alerta",
        shapes=[
            dict(type="rect", xref="x", yref="paper", x0=0.0, x1=0.4, y0=0, y1=1, fillcolor="rgba(34,197,94,0.08)", line_width=0),
            dict(type="rect", xref="x", yref="paper", x0=0.4, x1=0.7, y0=0, y1=1, fillcolor="rgba(245,158,11,0.08)", line_width=0),
            dict(type="rect", xref="x", yref="paper", x0=0.7, x1=1.0, y0=0, y1=1, fillcolor="rgba(239,68,68,0.08)", line_width=0),
        ],
    )
    fig_risk = aplicar_estilo_grafico(fig_risk, percentual_x=True)
    st.plotly_chart(fig_risk, use_container_width=True)
    st.caption("❓ Quanto mais à direita e maior a bolha, maior o risco e o impacto operacional.")

with aba3:
    secao_com_ajuda(
        "Confiabilidade (chance de operar sem falha), Weibull (modelo de vida) e classificação do padrão de falha",
        "R(t) indica chance de não falhar; F(t) indica probabilidade acumulada de falha no tempo.",
    )
    intervalos = (
        base.sort_values(["equipamento_id", "dt_parada"])
        .groupby("equipamento_id")["dt_parada"]
        .diff()
        .dt.total_seconds()
        .div(3600.0)
        .dropna()
        .values
    )
    beta, eta = fit_weibull(intervalos)
    classe = classificar_falha_weibull(beta)

    c1, c2, c3 = st.columns(3)
    c1.metric("Beta Weibull", f"{beta:,.3f}" if not np.isnan(beta) else "Não informado")
    c2.metric("Eta Weibull (h)", f"{eta:,.1f}" if not np.isnan(eta) else "Não informado")
    c3.metric("Classe de falha", classe)

    if not np.isnan(beta) and not np.isnan(eta):
        tempo = np.linspace(1, max(np.nanmax(intervalos), 1), 200)
        r_t = np.exp(-((tempo / eta) ** beta))
        f_t = 1 - r_t
        curv = pd.DataFrame({"tempo_h": tempo, "R(t)": r_t, "F(t)": f_t})
        fig_weibull = px.line(
            curv,
            x="tempo_h",
            y=["R(t)", "F(t)"],
            title="Curvas de confiabilidade e probabilidade acumulada",
            labels={"tempo_h": "Tempo (h)", "value": "Probabilidade", "variable": "Indicador"},
        )
        fig_weibull.update_layout(xaxis_title="Tempo (h)", yaxis_title="Probabilidade")
        fig_weibull = aplicar_estilo_grafico(fig_weibull, percentual_y=True)
        st.plotly_chart(fig_weibull, use_container_width=True)
        st.caption("❓ R(t) cai ao longo do tempo; F(t) sobe. Beta define se a falha é infantil, aleatória ou desgaste.")
    else:
        st.info("Dados insuficientes para ajuste robusto de Weibull.")

with aba4:
    secao_com_ajuda(
        "Monte Carlo (simulação probabilística), cenários e impacto na produção",
        "Defina deslocamento (KM/HR) e quantidade de simulações para estimar risco de falha e tempo de parada esperado.",
    )
    st.caption(
        "Esta é a aba de simulação Monte Carlo (simulação por probabilidade). "
        "Ajuste deslocamento e quantidade de simulações no menu lateral."
    )
    alvo = st.selectbox("Equipamento para simulação", options=kpi["equipamento_id"].tolist())
    row = kpi[kpi["equipamento_id"] == alvo].iloc[0]
    dur_equip = base[base["equipamento_id"] == alvo]["duracao_h"].values
    if deslocamento_mc == "Automático (equipamento)":
        unidade_uso = "KM" if row["tipo_deslocamento"] == "KM" else "HR"
    else:
        unidade_uso = deslocamento_mc
    horizonte_evento = float(horizonte_km if unidade_uso == "KM" else horizonte_hr)
    lambda_evento = float(row["lambda_uso"])
    sim = simular_monte_carlo_equip(
        lambda_evento, dur_equip, horizonte_evento=horizonte_evento, n=qtd_simulacoes_mc
    )
    st.metric(
        f"Probabilidade (chance) de pelo menos 1 parada em {horizonte_evento:,.0f} {unidade_uso}",
        f"{(sim['falhas'] >= 1).mean() * 100:,.1f}%",
    )
    st.metric(f"Tempo de parada esperado em {horizonte_evento:,.0f} {unidade_uso} (h)", f"{sim['downtime_h'].mean():,.1f}")
    st.metric("Impacto de produção esperado (R$)", f"{sim['downtime_h'].mean() * prod_hora:,.2f}")
    fig_hist = px.histogram(
        sim,
        x="downtime_h",
        nbins=50,
        title=f"Distribuição de tempo de parada simulado - {alvo}",
        color_discrete_sequence=["#60a5fa"],
        labels={"downtime_h": "Tempo parado (h)", "count": "Quantidade"},
    )
    fig_hist.update_layout(xaxis_title="Tempo de parada (h)", yaxis_title="Frequência")
    fig_hist = aplicar_estilo_grafico(fig_hist)
    st.plotly_chart(fig_hist, use_container_width=True)
    st.caption("❓ Histograma: mostra a distribuição dos possíveis tempos de parada simulados.")

    st.markdown("**Animação da simulação (evolução das rodadas Monte Carlo)**")
    resumo_anim = sim.copy()
    resumo_anim["iteracao"] = np.arange(1, len(resumo_anim) + 1)
    resumo_anim["media_downtime"] = resumo_anim["downtime_h"].expanding().mean()
    resumo_anim["media_falhas"] = resumo_anim["falhas"].expanding().mean()
    passo_anim = max(1, len(resumo_anim) // max(1, etapas_anim_mc))
    resumo_anim["frame"] = ((resumo_anim["iteracao"] - 1) // passo_anim + 1).astype(int)
    anim_frame = (
        resumo_anim.groupby("frame")
        .agg(iteracao=("iteracao", "max"), media_downtime=("media_downtime", "last"), media_falhas=("media_falhas", "last"))
        .reset_index()
    )
    mapa_velocidade = {
        "Lenta": {"duration_ms": 120},
        "Normal": {"duration_ms": 70},
        "Rápida": {"duration_ms": 35},
        "Máxima": {"duration_ms": 15},
    }
    cfg_vel = mapa_velocidade.get(velocidade_anim_mc, mapa_velocidade["Rápida"])

    # Constrói frames cumulativos para uma animação contínua e fluida no cliente.
    quadros = []
    for f in anim_frame["frame"].tolist():
        parcial = anim_frame[anim_frame["frame"] <= f][["iteracao", "media_downtime", "media_falhas"]].copy()
        parcial["frame"] = f
        quadros.append(parcial)
    anim_cumul = pd.concat(quadros, ignore_index=True)
    anim_long = anim_cumul.melt(
        id_vars=["frame", "iteracao"],
        value_vars=["media_downtime", "media_falhas"],
        var_name="indicador",
        value_name="valor",
    )
    anim_long["indicador"] = anim_long["indicador"].map(
        {"media_downtime": "Média tempo de parada (h)", "media_falhas": "Média falhas"}
    )

    fig_anim = px.line(
        anim_long,
        x="iteracao",
        y="valor",
        color="indicador",
        animation_frame="frame",
        line_group="indicador",
        title="Animação: convergência da simulação",
        range_x=[1, len(resumo_anim)],
        range_y=[0, max(anim_long["valor"].max() * 1.15, 1)],
        color_discrete_map={"Média tempo de parada (h)": "#60a5fa", "Média falhas": "#f59e0b"},
        labels={"iteracao": "Número de simulações executadas", "valor": "Média acumulada", "frame": "Etapa"},
    )
    fig_anim.update_traces(mode="lines+markers", line=dict(width=3))
    fig_anim.update_layout(
        updatemenus=[{
            "type": "buttons",
            "showactive": False,
            "buttons": [
                {
                    "label": "▶ Reproduzir contínuo",
                    "method": "animate",
                    "args": [None, {"frame": {"duration": cfg_vel["duration_ms"], "redraw": True}, "transition": {"duration": 0}, "fromcurrent": True, "mode": "immediate"}],
                },
                {
                    "label": "⏹ Parar",
                    "method": "animate",
                    "args": [[None], {"frame": {"duration": 0, "redraw": False}, "mode": "immediate"}],
                },
            ],
            "direction": "left",
            "x": 0.0,
            "y": 1.18,
        }],
    )
    fig_anim = aplicar_estilo_grafico(fig_anim)
    st.plotly_chart(fig_anim, use_container_width=True)
    st.caption(
        "❓ Animação contínua: clique em ▶ Reproduzir contínuo para rodar sem pausas. "
        "A velocidade segue o seletor lateral."
    )

    st.markdown("**Simulação de cenários**")
    melhor = simular_monte_carlo_equip(float(row["lambda_uso"]) * 0.7, dur_equip * 0.85, horizonte_evento=horizonte_evento, n=max(1000, qtd_simulacoes_mc // 2))
    pior = simular_monte_carlo_equip(float(row["lambda_uso"]) * 1.3, dur_equip * 1.2, horizonte_evento=horizonte_evento, n=max(1000, qtd_simulacoes_mc // 2))
    cenarios = pd.DataFrame(
        {
            "cenario": ["Melhor caso", "Cenário base", "Pior caso"],
            "downtime_h": [melhor["downtime_h"].mean(), sim["downtime_h"].mean(), pior["downtime_h"].mean()],
        }
    )
    fig_cenarios = px.bar(
        cenarios,
        x="cenario",
        y="downtime_h",
        title="Comparação de cenários",
        color="cenario",
        color_discrete_map={"Melhor caso": "#22c55e", "Cenário base": "#60a5fa", "Pior caso": "#ef4444"},
        labels={"cenario": "Cenário", "downtime_h": "Tempo parado esperado (h)"},
    )
    fig_cenarios.update_layout(xaxis_title="Cenário", yaxis_title="Tempo de parada esperado (h)")
    fig_cenarios = aplicar_estilo_grafico(fig_cenarios)
    st.plotly_chart(fig_cenarios, use_container_width=True)
    st.caption("❓ Cenários comparam efeito de melhorias (melhor caso) ou degradação (pior caso).")

with aba5:
    secao_com_ajuda(
        "Custo corretiva vs preventiva, backlog (pendências), equipe e peças",
        "Compara impacto financeiro esperado e ajuda a decidir entre foco preventivo e corretivo.",
    )
    exp_falhas_uso = float(kpi["falhas_esperadas_uso"].sum())
    custo_corretiva_estimado = exp_falhas_uso * custo_corr
    custo_preventiva_estimado = len(kpi) * custo_prev * 0.25
    impacto_financeiro_parada = float(kpi["risco_financeiro_uso"].sum())

    c1, c2, c3 = st.columns(3)
    c1.metric("Custo corretiva no horizonte de uso (R$)", f"{custo_corretiva_estimado:,.2f}")
    c2.metric("Custo preventiva no horizonte de uso (R$)", f"{custo_preventiva_estimado:,.2f}")
    c3.metric("Impacto financeiro das paradas (R$)", f"{impacto_financeiro_parada:,.2f}")

    custos = pd.DataFrame(
        {
            "categoria": ["Corretiva", "Preventiva", "Paradas"],
            "valor": [custo_corretiva_estimado, custo_preventiva_estimado, impacto_financeiro_parada],
        }
    )
    fig_custos = px.bar(
        custos,
        x="categoria",
        y="valor",
        title="Análise de impacto financeiro",
        color="categoria",
        color_discrete_map={"Corretiva": "#ef4444", "Preventiva": "#22c55e", "Paradas": "#f59e0b"},
        labels={"categoria": "Categoria", "valor": "Valor (R$)"},
    )
    fig_custos.update_layout(xaxis_title="Categoria", yaxis_title="Valor (R$)")
    fig_custos = aplicar_estilo_grafico(fig_custos)
    st.plotly_chart(fig_custos, use_container_width=True)
    st.caption("❓ Valores maiores indicam onde está o maior peso financeiro no horizonte analisado.")

    backlog = int(raw["DT_SAIDA"].isna().sum()) if "DT_SAIDA" in raw.columns else 0
    tmi = float(base.sort_values(["equipamento_id", "dt_parada"]).groupby("equipamento_id")["dt_parada"].diff().dt.total_seconds().div(3600).mean())
    eficiencia = (
        base["previsao_h"].sum() / base["duracao_h"].sum()
        if base["previsao_h"].notna().sum() > 0 and base["duracao_h"].sum() > 0
        else np.nan
    )

    st.write(f"**Backlog de manutenção (OS sem retorno):** {backlog}")
    st.write(f"**Tempo médio entre intervenções (h):** {tmi:,.1f}" if not np.isnan(tmi) else "**Tempo médio entre intervenções:** Não informado")
    st.write(f"**Eficiência da equipe (previsão/real):** {eficiencia * 100:,.1f}%" if not np.isnan(eficiencia) else "**Eficiência da equipe:** sem dados de PREVISÃO")

    sobressalentes = base.groupby("tipo_falha").size().sort_values(ascending=False).head(10).reset_index(name="ocorrencias")
    fig_pecas = px.bar(
        sobressalentes,
        x="tipo_falha",
        y="ocorrencias",
        title="Previsão de necessidade de peças por tipo de falha",
        color="ocorrencias",
        color_continuous_scale="Oranges",
        labels={"tipo_falha": "Tipo de falha", "ocorrencias": "Quantidade"},
    )
    fig_pecas.update_layout(xaxis_title="Tipo de falha", yaxis_title="Ocorrências")
    fig_pecas = aplicar_estilo_grafico(fig_pecas)
    st.plotly_chart(fig_pecas, use_container_width=True)
    st.caption("❓ Tipos de falha com maior ocorrência tendem a demandar mais peças sobressalentes.")

    recomendacoes = (
        kpi.sort_values("crit_score", ascending=False)[
            ["equipamento_id", "tipo_falha_top", "tipo_deslocamento", "intervalo_prev_uso", "sugestao_plano"]
        ]
        .head(15)
        .rename(columns={"intervalo_prev_uso": "intervalo_preventivo_uso"})
    )
    st.dataframe(recomendacoes, use_container_width=True)

st.success(f"Análise concluída para {len(base):,} registros ({janela}). Referência: {referencia}.")
