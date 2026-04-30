"""
Analise de confiabilidade por Weibull.
"""

from typing import List, NamedTuple, Tuple

import numpy as np
import pandas as pd


class CurvaConfiabilidade(NamedTuple):
    t: list[float]
    R_t: list[float]
    h_t: list[float]
    f_t: list[float]
    b10: float
    b50: float
    b90: float
    eta: float
    beta: float
    t_atual: float


def calcular_curva_confiabilidade(beta: float, eta: float, t_atual: float = 0, n_pontos: int = 200) -> CurvaConfiabilidade:
    t_max = eta * 3
    t = np.linspace(0.01, t_max, n_pontos)
    r_t = np.exp(-np.power(t / eta, beta))
    h_t = (beta / eta) * np.power(t / eta, beta - 1)
    f_t = h_t * r_t

    def bx(x: float) -> float:
        return float(eta * np.power(-np.log(1 - x / 100), 1 / beta))

    return CurvaConfiabilidade(
        t=t.tolist(),
        R_t=r_t.tolist(),
        h_t=h_t.tolist(),
        f_t=f_t.tolist(),
        b10=round(bx(10), 1),
        b50=round(bx(50), 1),
        b90=round(bx(90), 1),
        eta=round(float(eta), 1),
        beta=round(float(beta), 3),
        t_atual=round(float(t_atual), 1),
    )


def calcular_confiabilidade_atual(beta: float, eta: float, t: float) -> float:
    return float(np.exp(-np.power(t / eta, beta)))


def pontos_papel_weibull(intervalos_reais: list[float], beta: float, eta: float) -> Tuple[List[dict], List[dict]]:
    """
    Papel de Weibull: eixo x = ln(t), regressão y = beta * ln(t) - beta * ln(eta) + ln(-ln(1-F)).
    Retorna pontos observados e linha ajustada no mesmo domínio numérico para plot.
    """
    if len(intervalos_reais) < 3:
        return [], []
    dados = np.sort(np.array(intervalos_reais, dtype=float))
    n = len(dados)
    f_emp = (np.arange(1, n + 1) - 0.3) / (n + 0.4)
    f_emp = np.clip(f_emp, 1e-6, 1 - 1e-6)
    y_obs = np.log(-np.log(1 - f_emp))
    x_obs = np.log(np.clip(dados, 1e-9, None))
    pontos_obs = [{"ln_t": round(float(x_obs[i]), 4), "y": round(float(y_obs[i]), 4)} for i in range(n)]
    t_lin = np.linspace(max(float(np.min(dados)), 1e-6), float(np.max(dados)) * 1.2, 80)
    x_lin = np.log(t_lin)
    y_lin = beta * (np.log(t_lin) - np.log(eta))
    linha = [{"ln_t": round(float(x_lin[i]), 4), "y": round(float(y_lin[i]), 4)} for i in range(len(t_lin))]
    return pontos_obs, linha


def calcular_curva_banheira_grupo(df_grupo: pd.DataFrame) -> dict:
    from .monte_carlo import extrair_intervalos_falha

    betas = []
    etas = []
    for cod in df_grupo["cod_equipamento"].dropna().unique():
        try:
            dist = extrair_intervalos_falha(df_grupo[df_grupo["cod_equipamento"] == cod])
            betas.append(dist.beta)
            etas.append(dist.eta)
        except Exception:
            continue
    if not betas:
        return {}
    beta_medio = float(np.median(betas))
    eta_medio = float(np.median(etas))
    if beta_medio < 0.9:
        fase = "MORTALIDADE_INFANTIL"
    elif beta_medio < 1.1:
        fase = "VIDA_UTIL"
    else:
        fase = "DESGASTE"
    return {
        "beta_medio": round(beta_medio, 3),
        "eta_medio": round(eta_medio, 1),
        "fase_frota": fase,
        "n_equipamentos_analisados": len(betas),
        "curva": calcular_curva_confiabilidade(beta_medio, eta_medio)._asdict(),
    }
