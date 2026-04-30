"""
Simulacao de Monte Carlo para previsao de falhas.
"""

from dataclasses import dataclass
from typing import Optional
import logging

import numpy as np
import pandas as pd
from scipy import stats

logger = logging.getLogger(__name__)

N_SIMULACOES_PADRAO = 10_000


@dataclass
class ResultadoMonteCarlo:
    cod_equipamento: Optional[int]
    grupo: str
    modelo: str
    unidade_medida: str
    n_simulacoes: int
    weibull_beta: float
    weibull_eta: float
    weibull_interpretacao: str
    r_quadrado: float
    mtbf_simulado: float
    desvio_padrao: float
    p10: float
    p25: float
    p50: float
    p75: float
    p90: float
    prob_falha_30d: float
    prob_falha_60d: float
    prob_falha_90d: float
    prob_falha_safra: float
    intervalo_preventiva_otimo: float
    proxima_manutencao_estimada: str
    dias_ate_p50: Optional[float] = None
    dias_ate_p90: Optional[float] = None
    horizontes_uso: Optional[list] = None
    probs_por_horizonte_uso: Optional[list] = None
    histograma_residual: Optional[list] = None
    cdf_residual: Optional[list] = None


@dataclass
class DistribuicaoFalhas:
    intervalos_reais: list[float]
    n_observacoes: int
    media: float
    desvio: float
    minimo: float
    maximo: float
    beta: float
    eta: float
    gamma: float
    distribuicao_melhor: str
    ks_pvalue: float


def _selecionar_melhor_distribuicao(dados: np.ndarray) -> str:
    resultados = {}
    for nome, dist in {"weibull": stats.weibull_min, "exponential": stats.expon, "lognormal": stats.lognorm}.items():
        try:
            params = dist.fit(dados, floc=0)
            log_lik = np.sum(dist.logpdf(dados, *params))
            k = len(params)
            resultados[nome] = 2 * k - 2 * log_lik
        except Exception:
            continue
    return min(resultados, key=resultados.get) if resultados else "weibull"


def extrair_intervalos_falha(df_ativo: pd.DataFrame, usar_km_hr: bool = True) -> DistribuicaoFalhas:
    df = df_ativo[df_ativo["is_falha_real"] == True].sort_values("dt_entrada").copy()
    if len(df) < 3:
        raise ValueError(f"Minimo 3 falhas. Encontradas: {len(df)}")
    intervalos = []
    if usar_km_hr and df["acumulado_km_hr"].notna().sum() >= len(df) * 0.7:
        acumulados = df["acumulado_km_hr"].dropna().sort_values()
        diffs = acumulados.diff().dropna()
        intervalos = diffs[diffs > 0].tolist()
    else:
        for i in range(1, len(df)):
            fim_anterior = df["dt_saida"].iloc[i - 1]
            inicio_atual = df["dt_entrada"].iloc[i]
            if pd.notna(fim_anterior) and pd.notna(inicio_atual):
                h = (inicio_atual - fim_anterior).total_seconds() / 3600
                if h > 0:
                    intervalos.append(h)
    if len(intervalos) < 2:
        raise ValueError("Intervalos insuficientes para ajuste")

    dados = np.array(intervalos)
    try:
        shape, loc, scale = stats.weibull_min.fit(dados, floc=0)
        ks_stat, ks_pvalue = stats.kstest(dados, "weibull_min", args=(shape, loc, scale))
        del ks_stat
        beta, gamma, eta = shape, loc, scale
    except Exception as exc:
        logger.warning("Falha ajuste Weibull: %s", exc)
        beta, gamma, eta, ks_pvalue = 1.0, 0.0, float(np.mean(dados)), 0.0

    return DistribuicaoFalhas(
        intervalos_reais=dados.tolist(),
        n_observacoes=len(dados),
        media=float(np.mean(dados)),
        desvio=float(np.std(dados)),
        minimo=float(np.min(dados)),
        maximo=float(np.max(dados)),
        beta=float(beta),
        eta=float(eta),
        gamma=float(gamma),
        distribuicao_melhor=_selecionar_melhor_distribuicao(dados),
        ks_pvalue=float(ks_pvalue),
    )


def calcular_r_quadrado_weibull(dist: DistribuicaoFalhas) -> float:
    if len(dist.intervalos_reais) < 3:
        return 0.0
    dados = np.sort(dist.intervalos_reais)
    n = len(dados)
    f_emp = (np.arange(1, n + 1) - 0.3) / (n + 0.4)
    f_teo = 1 - np.exp(-np.power(dados / dist.eta, dist.beta))
    ss_res = np.sum((f_emp - f_teo) ** 2)
    ss_tot = np.sum((f_emp - np.mean(f_emp)) ** 2)
    return float(1 - ss_res / ss_tot) if ss_tot > 0 else 0.0


def calcular_intervalo_otimo_preventiva(
    dist: DistribuicaoFalhas, custo_preventiva: float = 1.0, custo_corretiva: float = 10.0
) -> float:
    from scipy.optimize import minimize_scalar

    def custo_unitario(t):
        if t <= 0:
            return np.inf
        r_t = np.exp(-np.power(t / dist.eta, dist.beta))
        custo = custo_preventiva + custo_corretiva * (1 - r_t)
        integral = dist.eta * stats.gamma.cdf(np.power(t / dist.eta, dist.beta), 1 + 1 / dist.beta) * (1 / dist.beta)
        return np.inf if integral <= 0 else custo / max(integral, 0.001)

    res = minimize_scalar(custo_unitario, bounds=(dist.minimo * 0.5, dist.eta * 3), method="bounded")
    return float(max(res.x, dist.minimo * 0.5))


def simular_monte_carlo(
    dist: DistribuicaoFalhas,
    horimetro_atual: float,
    unidade_medida: str = "HM",
    uso_diario_estimado: float = 16.0,
    n_simulacoes: int = N_SIMULACOES_PADRAO,
    horizonte_horas: float = 2160,
    seed: int = 42,
) -> ResultadoMonteCarlo:
    del horizonte_horas
    rng = np.random.default_rng(seed)
    uso_atual = max(float(horimetro_atual), 0.0)

    # Probabilidade acumulada no uso atual (CDF Weibull em t=uso_atual)
    if uso_atual <= dist.gamma:
        f_atual = 0.0
    else:
        base = max((uso_atual - dist.gamma) / max(dist.eta, 1e-9), 0.0)
        f_atual = float(1 - np.exp(-np.power(base, dist.beta)))
    f_atual = float(min(max(f_atual, 0.0), 0.999999))

    # Amostragem condicional: T | T > uso_atual
    u = rng.uniform(f_atual, 0.999999999, n_simulacoes)
    tempos_ate_falha = dist.gamma + dist.eta * np.power(-np.log(1 - u), 1 / dist.beta)
    tempos_residuais = np.maximum(tempos_ate_falha - uso_atual, 0.0)

    def prob_falha(h):
        return float(np.mean(tempos_residuais <= h) * 100)

    unidade_norm = (unidade_medida or "HM").upper()
    if unidade_norm == "HR":
        unidade_norm = "HM"
    # Horizonte operacional em UNIDADE DE USO (não em dia calendário)
    if unidade_norm == "KM":
        horizontes_uso = [500, 1000, 2000, 4000]
    else:
        horizontes_uso = [50, 100, 200, 400]
    probs_uso = [round(prob_falha(h), 1) for h in horizontes_uso]
    p10, p25, p50, p75, p90 = np.percentile(tempos_residuais, [10, 25, 50, 75, 90])
    intervalo_otimo = calcular_intervalo_otimo_preventiva(dist)
    if dist.beta < 0.9:
        interpretacao = "FALHAS INFANTIS"
    elif dist.beta < 1.1:
        interpretacao = "FALHAS ALEATORIAS"
    elif dist.beta < 2.5:
        interpretacao = "DESGASTE GRADUAL"
    else:
        interpretacao = "DESGASTE ACELERADO"

    hi = float(np.percentile(tempos_residuais, 99.9))
    hi = max(hi, float(np.max(tempos_residuais)) + 1e-6)
    bins = np.linspace(0, hi, 21)
    counts, edges = np.histogram(tempos_residuais, bins=bins)
    histograma_residual = [{"x0": round(float(edges[i]), 2), "x1": round(float(edges[i + 1]), 2), "count": int(counts[i])} for i in range(len(counts))]
    xs = np.linspace(0, hi, 40)
    cdf_residual = [{"t": round(float(x), 2), "F": round(float(np.mean(tempos_residuais <= x)), 4)} for x in xs]
    uso_dia = max(float(uso_diario_estimado), 1e-6)
    dias_p50 = float(p50 / uso_dia)
    dias_p90 = float(p90 / uso_dia)

    return ResultadoMonteCarlo(
        cod_equipamento=None,
        grupo="",
        modelo="",
        unidade_medida=unidade_norm,
        n_simulacoes=n_simulacoes,
        weibull_beta=round(dist.beta, 3),
        weibull_eta=round(dist.eta, 1),
        weibull_interpretacao=interpretacao,
        r_quadrado=round(calcular_r_quadrado_weibull(dist), 3),
        mtbf_simulado=round(float(np.mean(tempos_ate_falha)), 1),
        desvio_padrao=round(float(np.std(tempos_ate_falha)), 1),
        p10=round(float(p10), 1),
        p25=round(float(p25), 1),
        p50=round(float(p50), 1),
        p75=round(float(p75), 1),
        p90=round(float(p90), 1),
        horizontes_uso=horizontes_uso,
        probs_por_horizonte_uso=probs_uso,
        # Compatibilidade legada (mantidos, mas derivados de uso)
        prob_falha_30d=probs_uso[0],
        prob_falha_60d=probs_uso[1],
        prob_falha_90d=probs_uso[2],
        prob_falha_safra=probs_uso[3],
        intervalo_preventiva_otimo=round(intervalo_otimo, 0),
        proxima_manutencao_estimada=f"P50: {p50:.0f}{unidade_norm} (~{dias_p50:.1f}d) | P90: {p90:.0f}{unidade_norm} (~{dias_p90:.1f}d)",
        dias_ate_p50=round(dias_p50, 1),
        dias_ate_p90=round(dias_p90, 1),
        histograma_residual=histograma_residual,
        cdf_residual=cdf_residual,
    )


def simular_frota_completa(df: pd.DataFrame, grupos: list = None, n_simulacoes: int = 10_000) -> pd.DataFrame:
    if grupos:
        df = df[df["grupo_equipamento"].isin(grupos)]
    resultados = []
    for cod in df["cod_equipamento"].dropna().unique():
        df_ativo = df[df["cod_equipamento"] == cod]
        try:
            dist = extrair_intervalos_falha(df_ativo)
            horimetro = (
                float(df_ativo["km_hr_percorrido"].dropna().tail(1).iloc[0]) if df_ativo["km_hr_percorrido"].notna().any() else 0.0
            )
            unidade = str(df_ativo["unidade_medida"].iloc[0]) if "unidade_medida" in df_ativo.columns else "HM"
            sim = simular_monte_carlo(dist, horimetro, unidade_medida=unidade, n_simulacoes=n_simulacoes)
            sim.cod_equipamento = int(cod)
            sim.grupo = str(df_ativo["grupo_equipamento"].iloc[0])
            sim.modelo = str(df_ativo["modelo"].iloc[0])
            sim.unidade_medida = unidade
            resultados.append(sim)
        except ValueError:
            continue
        except Exception as exc:
            logger.warning("Erro simulacao equipamento %s: %s", cod, exc)
    if not resultados:
        return pd.DataFrame()
    out = pd.DataFrame([vars(r) for r in resultados])
    return out.sort_values("prob_falha_90d", ascending=False)
