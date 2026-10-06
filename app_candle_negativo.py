import os
import pandas as pd
import streamlit as st
import yfinance as yf

# ============================================================
# CONFIGURAÇÕES DA PÁGINA
# ============================================================
st.set_page_config(
    page_title="Varredura de Ativos B3",
    page_icon="📈",
    layout="centered"
)

# ============================================================
# CONFIGURAÇÕES
# ============================================================
ARQUIVO_PADRAO = "IBOVDia_300925_sem_duplicadas_rev02.csv"

# REGRA 1
# Sombra inferior deve representar pelo menos
# 20% do corpo do candle negativo.
PERCENTUAL_MINIMO_SOMBRA_CORPO = 20.0

# REGRA 2
# Sombra inferior deve representar pelo menos
# 20% da distância entre máxima e fechamento.
PERCENTUAL_MINIMO_SOMBRA_MAX_FECHAMENTO = 20.0

MESES = {
    "Janeiro": 1,
    "Fevereiro": 2,
    "Março": 3,
    "Abril": 4,
    "Maio": 5,
    "Junho": 6,
    "Julho": 7,
    "Agosto": 8,
    "Setembro": 9,
    "Outubro": 10,
    "Novembro": 11,
    "Dezembro": 12
}

# ============================================================
# CARREGAR TICKERS
# ============================================================
def carregar_tickers(arquivo):
    df = pd.read_csv(
        arquivo,
        header=None,
        names=["Ticker"],
        dtype=str
    )

    if df.empty:
        raise ValueError("O arquivo CSV está vazio.")

    tickers = (
        df["Ticker"]
        .dropna()
        .astype(str)
        .str.strip()
        .str.upper()
        .tolist()
    )

    tickers_normalizados = []

    for ticker in tickers:
        if not ticker:
            continue

        if not ticker.endswith(".SA"):
            ticker = ticker + ".SA"

        tickers_normalizados.append(ticker)

    return list(dict.fromkeys(tickers_normalizados))

# ============================================================
# REMOVER TIMEZONE
# ============================================================
def remover_timezone(dados):
    dados = dados.copy()

    if getattr(dados.index, "tz", None) is not None:
        dados.index = dados.index.tz_localize(None)

    return dados

# ============================================================
# CALCULAR CORPO DO CANDLE NEGATIVO
#
# Somente candle negativo:
#
# corpo = abertura - fechamento
# ============================================================
def calcular_corpo_negativo(
    abertura,
    fechamento
):
    return (
        abertura
        -
        fechamento
    )

# ============================================================
# CALCULAR SOMBRA INFERIOR DO CANDLE NEGATIVO
#
# sombra inferior = fechamento - mínima
# ============================================================
def calcular_sombra_inferior_negativa(
    fechamento,
    minima
):
    sombra = (
        fechamento
        -
        minima
    )

    return max(
        sombra,
        0
    )

# ============================================================
# REGRA 1
#
# 1. CANDLE OBRIGATORIAMENTE NEGATIVO:
#
# fechamento < abertura
#
# 2. SOMBRA INFERIOR >= 20% DO CORPO
#
# corpo = abertura - fechamento
#
# sombra inferior = fechamento - mínima
#
# condição:
#
# sombra inferior >= corpo × 20%
# ============================================================
def verificar_regra_1(
    abertura,
    fechamento,
    minima
):
    # Candle precisa ser negativo
    if fechamento >= abertura:
        return False

    corpo = calcular_corpo_negativo(
        abertura,
        fechamento
    )

    sombra_inferior = (
        calcular_sombra_inferior_negativa(
            fechamento,
            minima
        )
    )

    if corpo <= 0:
        return False

    sombra_minima_exigida = (
        corpo
        *
        (
            PERCENTUAL_MINIMO_SOMBRA_CORPO
            /
            100
        )
    )

    return (
        sombra_inferior
        >=
        sombra_minima_exigida
    )

# ============================================================
# REGRA 2
#
# SOMBRA INFERIOR >= 20% DA DISTÂNCIA:
#
# máxima - fechamento
#
# condição:
#
# sombra inferior >=
# (máxima - fechamento) × 20%
# ============================================================
def verificar_regra_2(
    maxima,
    fechamento,
    minima
):
    sombra_inferior = (
        calcular_sombra_inferior_negativa(
            fechamento,
            minima
        )
    )

    distancia_maxima_fechamento = (
        maxima
        -
        fechamento
    )

    if distancia_maxima_fechamento <= 0:
        return False

    sombra_minima_exigida = (
        distancia_maxima_fechamento
        *
        (
            PERCENTUAL_MINIMO_SOMBRA_MAX_FECHAMENTO
            /
            100
        )
    )

    return (
        sombra_inferior
        >=
        sombra_minima_exigida
    )

# ============================================================
# BUSCAR CANDLE ANTERIOR
# ============================================================
@st.cache_data(
    ttl=1800,
    show_spinner=False
)
def buscar_candle_anterior(
    ticker,
    tempo_grafico,
    ano,
    mes
):
    periodo_selecionado = pd.Period(
        year=ano,
        month=mes,
        freq="M"
    )

    # Busca histórico suficiente para mensal
    # e para construção dos trimestres.
    data_inicio = (
        periodo_selecionado - 18
    ).start_time

    data_fim = (
        periodo_selecionado + 1
    ).start_time + pd.Timedelta(days=2)

    dados_mensais = yf.Ticker(
        ticker
    ).history(
        start=data_inicio.strftime("%Y-%m-%d"),
        end=data_fim.strftime("%Y-%m-%d"),
        interval="1mo",
        auto_adjust=False,
        actions=False
    )

    if dados_mensais.empty:
        return None, "Sem dados no Yahoo Finance"

    dados_mensais = remover_timezone(
        dados_mensais
    )

    dados_mensais = dados_mensais.dropna(
        subset=[
            "Open",
            "High",
            "Low",
            "Close"
        ]
    )

    if dados_mensais.empty:
        return None, "Sem candles válidos"

    # Não utilizar meses posteriores
    # ao período escolhido.
    periodos_mensais = (
        dados_mensais
        .index
        .to_period("M")
    )

    dados_mensais = dados_mensais[
        periodos_mensais
        <=
        periodo_selecionado
    ]

    periodos_mensais = (
        dados_mensais
        .index
        .to_period("M")
    )

    # ========================================================
    # MENSAL
    #
    # Exemplo:
    #
    # selecionado = outubro/2026
    #
    # candle analisado = setembro/2026
    # ========================================================
    if tempo_grafico == "mensal":

        periodo_anterior = (
            periodo_selecionado - 1
        )

        linhas_anterior = dados_mensais[
            periodos_mensais
            ==
            periodo_anterior
        ]

        if linhas_anterior.empty:
            return (
                None,
                f"Sem dados para "
                f"{periodo_anterior.strftime('%m/%Y')}"
            )

        candle_anterior = (
            linhas_anterior.iloc[-1]
        )

        return (
            candle_anterior,
            None
        )

    # ========================================================
    # TRIMESTRAL
    #
    # T1 = JAN + FEV + MAR
    # T2 = ABR + MAI + JUN
    # T3 = JUL + AGO + SET
    # T4 = OUT + NOV + DEZ
    #
    # Exemplo:
    #
    # selecionado = outubro/2026
    #
    # candle analisado:
    # JUL + AGO + SET/2026
    # ========================================================
    if tempo_grafico == "trimestral":

        dados_trimestrais = (
            dados_mensais
            .resample("QS-JAN")
            .agg({
                "Open": "first",
                "High": "max",
                "Low": "min",
                "Close": "last",
                "Volume": "sum"
            })
        )

        dados_trimestrais = (
            dados_trimestrais.dropna(
                subset=[
                    "Open",
                    "High",
                    "Low",
                    "Close"
                ]
            )
        )

        mes_inicio_trimestre = (
            (
                (mes - 1)
                //
                3
            )
            *
            3
            +
            1
        )

        inicio_trimestre_atual = (
            pd.Timestamp(
                year=ano,
                month=mes_inicio_trimestre,
                day=1
            )
        )

        inicio_trimestre_anterior = (
            inicio_trimestre_atual
            -
            pd.DateOffset(months=3)
        )

        if (
            inicio_trimestre_anterior
            not in
            dados_trimestrais.index
        ):
            return (
                None,
                "Sem dados para o "
                "trimestre anterior"
            )

        candle_anterior = (
            dados_trimestrais.loc[
                inicio_trimestre_anterior
            ]
        )

        return (
            candle_anterior,
            None
        )

    return (
        None,
        "Tempo gráfico inválido"
    )

# ============================================================
# ANALISAR ATIVO
# ============================================================
def analisar_ativo(
    ticker,
    tempo_grafico,
    ano,
    mes
):
    (
        candle_anterior,
        erro
    ) = buscar_candle_anterior(
        ticker,
        tempo_grafico,
        ano,
        mes
    )

    if erro is not None:
        return False, erro

    abertura = float(
        candle_anterior["Open"]
    )

    maxima = float(
        candle_anterior["High"]
    )

    minima = float(
        candle_anterior["Low"]
    )

    fechamento = float(
        candle_anterior["Close"]
    )

    # ========================================================
    # PREÇOS INVÁLIDOS
    # ========================================================
    if (
        abertura <= 0
        or maxima <= 0
        or minima <= 0
        or fechamento <= 0
    ):
        return (
            False,
            "Preço inválido ou zerado"
        )

    # ========================================================
    # REGRA 1
    #
    # Candle anterior deve ser negativo.
    #
    # fechamento < abertura
    #
    # sombra inferior >= 20% do corpo
    # ========================================================
    passou_regra_1 = (
        verificar_regra_1(
            abertura,
            fechamento,
            minima
        )
    )

    # ========================================================
    # REGRA 2
    #
    # sombra inferior >= 20% de:
    #
    # máxima - fechamento
    # ========================================================
    passou_regra_2 = (
        verificar_regra_2(
            maxima,
            fechamento,
            minima
        )
    )

    # ========================================================
    # RESULTADO FINAL
    #
    # SOMENTE REGRAS 1 E 2
    # ========================================================
    passou = (
        passou_regra_1
        and
        passou_regra_2
    )

    return passou, None

# ============================================================
# INTERFACE
# ============================================================
st.title(
    "📈 Varredura de Candles B3"
)

st.write(
    "Seleção de candles negativos "
    "com sombra inferior relevante."
)

# ============================================================
# TEMPO GRÁFICO
# ============================================================
tempo_escolhido = st.radio(
    "Tempo gráfico:",
    [
        "Mensal",
        "Trimestral"
    ],
    horizontal=True
)

tempo_grafico = (
    tempo_escolhido.lower()
)

# ============================================================
# PERÍODO DA ANÁLISE
# ============================================================
st.subheader(
    "Período da análise"
)

hoje = pd.Timestamp.now()

anos_disponiveis = list(
    range(
        hoje.year,
        1999,
        -1
    )
)

coluna_mes, coluna_ano = (
    st.columns(2)
)

with coluna_mes:

    nome_mes_selecionado = (
        st.selectbox(
            "Mês:",
            list(MESES.keys()),
            index=hoje.month - 1
        )
    )

with coluna_ano:

    ano_selecionado = (
        st.selectbox(
            "Ano:",
            anos_disponiveis,
            index=0
        )
    )

mes_selecionado = (
    MESES[
        nome_mes_selecionado
    ]
)

periodo_selecionado = pd.Period(
    year=ano_selecionado,
    month=mes_selecionado,
    freq="M"
)

periodo_atual = (
    hoje.to_period("M")
)

# ============================================================
# MOSTRAR QUAL CANDLE SERÁ ANALISADO
# ============================================================
if periodo_selecionado > periodo_atual:

    st.warning(
        "O período selecionado está no futuro."
    )

elif tempo_grafico == "mensal":

    periodo_anterior = (
        periodo_selecionado - 1
    )

    st.info(
        f"Candle analisado: "
        f"{periodo_anterior.strftime('%m/%Y')}"
    )

else:

    mes_inicio_trimestre = (
        (
            (mes_selecionado - 1)
            //
            3
        )
        *
        3
        +
        1
    )

    inicio_trimestre_atual = pd.Period(
        year=ano_selecionado,
        month=mes_inicio_trimestre,
        freq="M"
    )

    inicio_trimestre_anterior = (
        inicio_trimestre_atual - 3
    )

    fim_trimestre_anterior = (
        inicio_trimestre_atual - 1
    )

    st.info(
        f"Candle trimestral analisado: "
        f"{inicio_trimestre_anterior.strftime('%m/%Y')} "
        f"até "
        f"{fim_trimestre_anterior.strftime('%m/%Y')}"
    )

# ============================================================
# LISTA DE ATIVOS
# ============================================================
st.subheader(
    "Lista de ativos"
)

arquivo_upload = st.file_uploader(
    "Selecione o arquivo CSV",
    type=["csv"]
)

if arquivo_upload is not None:

    arquivo_tickers = (
        arquivo_upload
    )

elif os.path.exists(
    ARQUIVO_PADRAO
):

    arquivo_tickers = (
        ARQUIVO_PADRAO
    )

else:

    arquivo_tickers = None

    st.warning(
        "Selecione um arquivo CSV "
        "contendo os códigos dos ativos."
    )

# ============================================================
# REGRAS
# ============================================================
with st.expander(
    "Ver regras da seleção"
):

    st.write(
        "1. O candle anterior deve ser negativo: "
        "fechamento menor que abertura. "
        "A sombra inferior deve representar pelo menos "
        "20% do corpo do candle."
    )

    st.write(
        "2. A sombra inferior também deve representar "
        "pelo menos 20% da distância entre "
        "a máxima e o fechamento do candle."
    )

    st.write(
        "Somente essas duas regras são utilizadas "
        "na seleção dos ativos."
    )

# ============================================================
# EXECUTAR
# ============================================================
if st.button(
    "Executar análise",
    type="primary",
    use_container_width=True
):

    if periodo_selecionado > periodo_atual:

        st.error(
            "Escolha um mês e ano "
            "que não estejam no futuro."
        )

        st.stop()

    if arquivo_tickers is None:

        st.error(
            "Selecione um arquivo CSV."
        )

        st.stop()

    try:

        tickers = carregar_tickers(
            arquivo_tickers
        )

    except Exception as erro:

        st.error(
            f"Erro ao carregar CSV: {erro}"
        )

        st.stop()

    ativos_encontrados = []
    erros = []

    total = len(tickers)

    barra = st.progress(0)
    status = st.empty()

    for numero, ticker in enumerate(
        tickers,
        start=1
    ):

        status.write(
            f"Analisando "
            f"{numero} de {total} "
            f"- {ticker}"
        )

        try:

            passou, erro = analisar_ativo(
                ticker,
                tempo_grafico,
                ano_selecionado,
                mes_selecionado
            )

            if passou:

                ativos_encontrados.append(
                    ticker
                )

            if erro is not None:

                erros.append(
                    (
                        ticker,
                        erro
                    )
                )

        except Exception as erro:

            erros.append(
                (
                    ticker,
                    str(erro)
                )
            )

        barra.progress(
            numero
            /
            total
        )

    status.empty()

    # ========================================================
    # RESULTADOS
    # ========================================================
    st.divider()

    st.subheader(
        "Ativos encontrados"
    )

    if ativos_encontrados:

        st.write(
            f"**Total: "
            f"{len(ativos_encontrados)}**"
        )

        df_resultados = pd.DataFrame({
            "Ativo": ativos_encontrados
        })

        st.dataframe(
            df_resultados,
            use_container_width=True,
            hide_index=True
        )

        csv_resultado = (
            df_resultados
            .to_csv(
                index=False
            )
            .encode(
                "utf-8-sig"
            )
        )

        st.download_button(
            "Baixar lista em CSV",
            data=csv_resultado,
            file_name=(
                f"ativos_"
                f"{tempo_grafico}_"
                f"{mes_selecionado:02d}_"
                f"{ano_selecionado}.csv"
            ),
            mime="text/csv"
        )

    else:

        st.warning(
            "Nenhum ativo atendeu "
            "às duas regras."
        )

    # ========================================================
    # ERROS
    # ========================================================
    if erros:

        with st.expander(
            f"Ativos sem dados ou "
            f"com erro: "
            f"{len(erros)}"
        ):

            for ticker, erro in erros:

                st.write(
                    f"{ticker}: "
                    f"{erro}"
                )
