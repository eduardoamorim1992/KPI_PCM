"""
Carregamento, limpeza e padronizacao dos dados da planilha PCM.
Entrada: parametro.xlsx
Saida: DataFrame normalizado e pronto para analise.
"""

from pathlib import Path
import logging

import pandas as pd

logger = logging.getLogger(__name__)

ARQUIVO_DADOS = Path("data/parametro.xlsx")
ABA_DADOS = "VW_ORDEM_SERVICO_SAF_PCM"
CACHE_PICKLE = Path("data/_cache_pcm.pkl.gz")

FALHAS_CORRETIVAS_REAIS = [
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
]

FALHAS_NAO_PRODUTIVAS = [
    "LIMPEZA INADEQUADA",
    "MANUTENCAO AGREGADOS",
    "SPOT",
    "MODIFICACAO/MELHORIA",
]


def _normalizar_texto_serie(serie: pd.Series) -> pd.Series:
    """Padroniza acentuacao/caixa/espacos para matching robusto."""
    return (
        serie.astype(str)
        .str.normalize("NFKD")
        .str.encode("ascii", errors="ignore")
        .str.decode("utf-8")
        .str.strip()
        .str.upper()
    )


def carregar_dados(filepath: Path = ARQUIVO_DADOS) -> pd.DataFrame:
    """Carrega planilha e retorna DataFrame normalizado para analise."""
    if not filepath.exists():
        # Em deploy (ex.: Vercel), o arquivo pode estar na raiz do projeto.
        candidatos = [
            Path("parametro.xlsx"),
            Path("../parametro.xlsx"),
            Path("./parametro.xlsx"),
        ]
        for alt in candidatos:
            if alt.exists():
                filepath = alt
                break

    if not filepath.exists():
        raise FileNotFoundError(
            "Arquivo de dados não encontrado. Esperado em 'data/parametro.xlsx' ou 'parametro.xlsx' na raiz do projeto."
        )

    # Cache em disco: reduz drasticamente o tempo de carga após a 1ª vez
    try:
        if CACHE_PICKLE.exists() and filepath.exists():
            if CACHE_PICKLE.stat().st_mtime >= filepath.stat().st_mtime:
                logger.info("Carregando cache %s", CACHE_PICKLE)
                return pd.read_pickle(CACHE_PICKLE, compression="gzip")
    except Exception as exc:
        logger.warning("Cache ignorado (erro): %s", exc)

    logger.info("Carregando dados de %s", filepath)
    # Ler apenas colunas necessárias melhora performance do openpyxl
    usecols = [
        "INSTANCIA",
        "NO_BOLETIM",
        "CD_EQUIPTO",
        "FG_ORIGEM",
        "CD_TRANSP",
        "DE_TRANSP",
        "FG_STATUS_OS",
        "CD_CLASMANU",
        "DE_MOTENTR",
        "DT_ENTRADA",
        "DT_SAIDA",
        "QT_HR_PERMAN",
        "DE_SERVICO",
        "ACM_KM_HR",
        "DE_MODELO",
        "DE_MARCA",
        "NO_ANOFABR",
        "DE_GRUPO_OP",
        "CD_UNIMED",
        "QT_KM_HR",
        "NO_HOR_ODOM",
    ]
    df = pd.read_excel(filepath, sheet_name=ABA_DADOS, engine="openpyxl", usecols=usecols)

    df = df.rename(
        columns={
            "INSTANCIA": "unidade",
            "NO_BOLETIM": "num_os",
            "CD_EQUIPTO": "cod_equipamento",
            "FG_ORIGEM": "origem_os",
            "CD_TRANSP": "cod_transportador",
            "DE_TRANSP": "nome_transportador",
            "FG_STATUS_OS": "status_os",
            "CD_CLASMANU": "classe_manutencao",
            "DE_MOTENTR": "tipo_falha",
            "DT_ENTRADA": "dt_entrada",
            "DT_SAIDA": "dt_saida",
            "QT_HR_PERMAN": "horas_parado",
            "DE_SERVICO": "descricao_servico",
            "ACM_KM_HR": "acumulado_km_hr",
            "DE_MODELO": "modelo",
            "DE_MARCA": "marca",
            "NO_ANOFABR": "ano_fabricacao",
            "DE_GRUPO_OP": "grupo_equipamento",
            "CD_UNIMED": "unidade_medida",
            "QT_KM_HR": "km_hr_percorrido",
            "NO_HOR_ODOM": "horimetro_referencia",
        }
    )

    df["dt_entrada"] = pd.to_datetime(df["dt_entrada"], errors="coerce")
    df["dt_saida"] = pd.to_datetime(df["dt_saida"], errors="coerce")
    df["horas_parado"] = pd.to_numeric(df["horas_parado"], errors="coerce")
    df["acumulado_km_hr"] = pd.to_numeric(df["acumulado_km_hr"], errors="coerce")
    df["km_hr_percorrido"] = pd.to_numeric(df["km_hr_percorrido"], errors="coerce")
    df["horimetro_referencia"] = pd.to_numeric(df["horimetro_referencia"], errors="coerce")
    df["ano_fabricacao"] = pd.to_numeric(df["ano_fabricacao"], errors="coerce").astype("Int64")
    df["cod_equipamento"] = pd.to_numeric(df["cod_equipamento"], errors="coerce").astype("Int64")
    df["num_os"] = pd.to_numeric(df["num_os"], errors="coerce").astype("Int64")

    for coluna in [
        "tipo_falha",
        "grupo_equipamento",
        "modelo",
        "marca",
        "unidade_medida",
        "origem_os",
        "status_os",
        "unidade",
    ]:
        df[coluna] = _normalizar_texto_serie(df[coluna])

    df["ano_mes"] = df["dt_entrada"].dt.to_period("M").astype(str)
    df["semana"] = df["dt_entrada"].dt.isocalendar().week.astype("Int64")
    df["mes"] = df["dt_entrada"].dt.month.astype("Int64")
    df["ano"] = df["dt_entrada"].dt.year.astype("Int64")
    df["dia_semana"] = df["dt_entrada"].dt.dayofweek.astype("Int64")
    df["hora_entrada"] = df["dt_entrada"].dt.hour.astype("Int64")

    df["is_falha_real"] = df["tipo_falha"].isin(FALHAS_CORRETIVAS_REAIS)
    df["is_produtiva"] = ~df["tipo_falha"].isin(FALHAS_NAO_PRODUTIVAS)

    df["tipo_manutencao"] = (
        df["origem_os"].map({"C": "CORRETIVA", "I": "PROGRAMADA", "T": "TERCEIRIZADA"}).fillna("OUTROS")
    )
    df["idade_anos"] = df["ano"].sub(df["ano_fabricacao"]).clip(lower=0)

    n_antes = len(df)
    df = df.dropna(subset=["dt_entrada", "cod_equipamento"])
    df = df[df["horas_parado"].fillna(0) >= 0]
    df = df[df["horas_parado"].fillna(0) <= 8760]
    n_depois = len(df)

    logger.info("Dados carregados: %s OS validas (removidas %s)", n_depois, n_antes - n_depois)
    df = df.reset_index(drop=True)

    # Persistir cache para próximas execuções
    try:
        CACHE_PICKLE.parent.mkdir(parents=True, exist_ok=True)
        df.to_pickle(CACHE_PICKLE, compression="gzip")
        logger.info("Cache salvo em %s", CACHE_PICKLE)
    except Exception as exc:
        logger.warning("Falha ao salvar cache: %s", exc)

    return df


def carregar_por_grupo(grupo: str) -> pd.DataFrame:
    df = carregar_dados()
    return df[df["grupo_equipamento"] == _normalizar_texto_serie(pd.Series([grupo])).iloc[0]].copy()


def carregar_por_equipamento(cod_equipamento: int) -> pd.DataFrame:
    df = carregar_dados()
    return df[df["cod_equipamento"] == cod_equipamento].sort_values("dt_entrada").copy()
