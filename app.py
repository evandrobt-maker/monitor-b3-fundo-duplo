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

# Candle positivo:
# corpo pode representar no máximo 25% da sombra inferior
PERCENTUAL_MAXIMO_CORPO_POSITIVO = 25.0

# Sombra inferior deve representar pelo menos
# 25% da amplitude total do candle
PERCENTUAL_MINIMO_SOMBRA = 25.0

# Mínima atual deve atingir pelo menos 80%
# da distância entre fechamento anterior e mínima anterior
PERCENTUAL_MINIMO_REPETICAO = 80.0

# Distância entre abertura atual e fechamento anterior
# não pode superar 15% da distância entre
# fechamento anterior e mínima anterior
PERCENTUAL_MAXIMO_DISTANCIA_ABERTURA = 15.0

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
# CALCULAR DISTÂNCIA PERCENTUAL
# ============================================================

def calcular_distancia_percentual(referencia, valor):
    if referencia == 0:
        return 0

    return ((referencia - valor) / referencia) * 100

# ============================================================
# CALCULAR SOMBRA INFERIOR
# ============================================================

def calcular_sombra_inferior(abertura, fechamento, minima):
    limite_inferior_corpo = min(
        abertura,
        fechamento
    )

    sombra_inferior = (
        limite_inferior_corpo
        -
        minima
    )

    return max(
        sombra_inferior,
        0
    )

# ============================================================
# PERCENTUAL DA SOMBRA INFERIOR
# ============================================================

def calcular_percentual_sombra_inferior(
    abertura,
    fechamento,
    maxima,
    minima
):
    amplitude_total = maxima - minima

    if amplitude_total <= 0:
        return 0

    sombra_inferior = calcular_sombra_inferior(
        abertura,
        fechamento,
        minima
    )

    return (
        sombra_inferior
        /
        amplitude_total
    ) * 100

# ============================================================
# VERIFICAR CANDLE POSITIVO
#
# Candle negativo = permitido
#
# Candle neutro = permitido
#
# Candle positivo:
# corpo deve representar no máximo 25%
# da sombra inferior
# ============================================================

def verificar_candle_positivo(
    abertura,
    fechamento,
    minima
):
    # Candle negativo
    if fechamento < abertura:
        return True

    # Candle neutro
    if fechamento == abertura:
        return True

    # Candle positivo
    corpo = fechamento - abertura

    sombra_inferior = (
        abertura - minima
    )

    if sombra_inferior <= 0:
        return False

    percentual_corpo_sombra = (
        corpo
        /
        sombra_inferior
    ) * 100

    return (
        percentual_corpo_sombra
        <=
        PERCENTUAL_MAXIMO_CORPO_POSITIVO
    )

# ============================================================
# DISTÂNCIA DA ABERTURA ATUAL
# ============================================================

def calcular_percentual_distancia_abertura(
    abertura_atual,
    fechamento_anterior,
    minima_anterior
):
    distancia_fechamento_minima = (
        fechamento_anterior
        -
        minima_anterior
    )

    if distancia_fechamento_minima <= 0:
        return float("inf")

    distancia_abertura = abs(
        abertura_atual
        -
        fechamento_anterior
    )

    return (
        distancia_abertura
        /
        distancia_fechamento_minima
    ) * 100

# ============================================================
# BUSCAR DADOS NO YAHOO FINANCE
# ============================================================

@st.cache_data(
    ttl=1800,
    show_spinner=False
)
def buscar_dados(
    ticker,
    tempo_grafico
):
    # ========================================================
    # MENSAL
    # ========================================================

    if tempo_grafico == "mensal":
        dados = yf.Ticker(ticker).history(
            period="6mo",
            interval="1mo",
            auto_adjust=False,
            actions=False
        )

        return dados

    # ========================================================
    # TRIMESTRAL
    #
    # 1º trimestre = JAN + FEV + MAR
    # 2º trimestre = ABR + MAI + JUN
    # 3º trimestre = JUL + AGO + SET
    # 4º trimestre = OUT + NOV + DEZ
    # ========================================================

    elif tempo_grafico == "trimestral":
        dados_mensais = yf.Ticker(ticker).history(
            period="2y",
            interval="1mo",
            auto_adjust=False,
            actions=False
        )

        if dados_mensais.empty:
            return dados_mensais

        dados_mensais = dados_mensais.dropna(
            subset=[
                "Open",
                "High",
                "Low",
                "Close"
            ]
        )

        dados_trimestrais = dados_mensais.resample(
            "QS-JAN"
        ).agg({
            "Open": "first",
            "High": "max",
            "Low": "min",
            "Close": "last",
            "Volume": "sum"
        })

        dados_trimestrais = dados_trimestrais.dropna(
            subset=[
                "Open",
                "High",
                "Low",
                "Close"
            ]
        )

        return dados_trimestrais

    else:
        raise ValueError(
            "Tempo gráfico inválido."
        )

# ============================================================
# ANALISAR ATIVO
# ============================================================

def analisar_ativo(
    ticker,
    tempo_grafico
):
    dados = buscar_dados(
        ticker,
        tempo_grafico
    )

    if dados.empty:
        return False, "Sem dados no Yahoo Finance"

    dados = dados.dropna(
        subset=[
            "Open",
            "High",
            "Low",
            "Close"
        ]
    )

    if len(dados) < 2:
        return False, "Menos de dois candles disponíveis"

    # ========================================================
    # CANDLE ATUAL
    # ========================================================

    candle_atual = dados.iloc[-1]

    abertura_atual = float(
        candle_atual["Open"]
    )

    minima_atual = float(
        candle_atual["Low"]
    )

    # ========================================================
    # CANDLE ANTERIOR
    # ========================================================

    candle_anterior = dados.iloc[-2]

    abertura_anterior = float(
        candle_anterior["Open"]
    )

    maxima_anterior = float(
        candle_anterior["High"]
    )

    minima_anterior = float(
        candle_anterior["Low"]
    )

    fechamento_anterior = float(
        candle_anterior["Close"]
    )

    # ========================================================
    # EVITAR PREÇOS INVÁLIDOS
    # ========================================================

    if (
        abertura_atual <= 0
        or abertura_anterior <= 0
        or fechamento_anterior <= 0
        or minima_anterior <= 0
        or minima_atual <= 0
        or maxima_anterior <= 0
    ):
        return False, "Preço inválido ou zerado"

    # ========================================================
    # FILTRO 1
    #
    # Candle negativo = permitido
    #
    # Candle positivo:
    # corpo <= 25% da sombra inferior
    # ========================================================

    formato_candle_valido = (
        verificar_candle_positivo(
            abertura_anterior,
            fechamento_anterior,
            minima_anterior
        )
    )

    # ========================================================
    # FILTRO 2
    #
    # Sombra inferior >= 25%
    # da amplitude total
    # ========================================================

    percentual_sombra_anterior = (
        calcular_percentual_sombra_inferior(
            abertura_anterior,
            fechamento_anterior,
            maxima_anterior,
            minima_anterior
        )
    )

    sombra_minima_25 = (
        percentual_sombra_anterior
        >=
        PERCENTUAL_MINIMO_SOMBRA
    )

    # ========================================================
    # FILTRO 3
    #
    # DISTÂNCIA:
    #
    # fechamento anterior -> mínima anterior
    # ========================================================

    distancia_anterior = (
        calcular_distancia_percentual(
            fechamento_anterior,
            minima_anterior
        )
    )

    # ========================================================
    # DISTÂNCIA:
    #
    # fechamento anterior -> mínima atual
    # ========================================================

    distancia_minima_atual = (
        calcular_distancia_percentual(
            fechamento_anterior,
            minima_atual
        )
    )

    distancia_minima_exigida = (
        distancia_anterior
        *
        (
            PERCENTUAL_MINIMO_REPETICAO
            /
            100
        )
    )

    atingiu_80_porcento = (
        distancia_minima_atual
        >=
        distancia_minima_exigida
    )

    # ========================================================
    # FILTRO 4
    #
    # Distância entre:
    #
    # abertura atual -> fechamento anterior
    #
    # deve ser no máximo 15% da distância:
    #
    # fechamento anterior -> mínima anterior
    # ========================================================

    percentual_distancia_abertura = (
        calcular_percentual_distancia_abertura(
            abertura_atual,
            fechamento_anterior,
            minima_anterior
        )
    )

    abertura_dentro_limite = (
        percentual_distancia_abertura
        <=
        PERCENTUAL_MAXIMO_DISTANCIA_ABERTURA
    )

    # ========================================================
    # RESULTADO FINAL
    # ========================================================

    passou = (
        formato_candle_valido
        and
        sombra_minima_25
        and
        atingiu_80_porcento
        and
        abertura_dentro_limite
    )

    return passou, None

# ============================================================
# INTERFACE
# ============================================================

st.title("📈 Varredura de Ativos B3")

st.write(
    "Escolha o tempo gráfico e execute a análise."
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
# ARQUIVO CSV
# ============================================================

st.subheader("Lista de ativos")

arquivo_upload = st.file_uploader(
    "Selecione o arquivo CSV",
    type=["csv"]
)

if arquivo_upload is not None:
    arquivo_tickers = arquivo_upload

elif os.path.exists(
    ARQUIVO_PADRAO
):
    arquivo_tickers = ARQUIVO_PADRAO

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
        "1. Candle negativo é permitido. "
        "Se o candle anterior for positivo, "
        "o corpo deve representar no máximo "
        "25% da sombra inferior."
    )

    st.write(
        "2. A sombra inferior do candle anterior "
        "deve representar pelo menos 25% "
        "da amplitude total."
    )

    st.write(
        "3. A mínima atual deve atingir pelo menos "
        "80% da distância entre o fechamento "
        "anterior e a mínima anterior."
    )

    st.write(
        "4. A distância entre a abertura atual "
        "e o fechamento anterior não pode superar "
        "15% da distância entre o fechamento "
        "anterior e a mínima anterior."
    )

# ============================================================
# EXECUTAR ANÁLISE
# ============================================================

if st.button(
    "Executar análise",
    type="primary",
    use_container_width=True
):
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
            f"Analisando {numero} de {total}"
        )

        try:
            passou, erro = analisar_ativo(
                ticker,
                tempo_grafico
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
            numero / total
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
            f"**Total: {len(ativos_encontrados)}**"
        )

        df_resultados = pd.DataFrame({
            "Ativo": ativos_encontrados
        })

        st.dataframe(
            df_resultados,
            use_container_width=True,
            hide_index=True
        )

        # ====================================================
        # DOWNLOAD DOS ATIVOS
        # ====================================================

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
                f"ativos_{tempo_grafico}.csv"
            ),
            mime="text/csv"
        )

    else:
        st.warning(
            "Nenhum ativo atendeu "
            "a todos os critérios."
        )

    # ========================================================
    # ERROS
    # ========================================================

    if erros:
        with st.expander(
            f"Ativos sem dados ou com erro: "
            f"{len(erros)}"
        ):
            for ticker, erro in erros:
                st.write(
                    f"{ticker}: {erro}"
                )
