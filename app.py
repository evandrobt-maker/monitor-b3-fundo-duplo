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

PERCENTUAL_MAXIMO_CORPO_POSITIVO = 25.0
PERCENTUAL_MINIMO_SOMBRA = 25.0
PERCENTUAL_MINIMO_REPETICAO = 80.0
PERCENTUAL_MAXIMO_DISTANCIA_FECHAMENTO = 10.0
PERCENTUAL_MAXIMO_DISTANCIA_ABERTURA = 15.0

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
# DISTÂNCIA PERCENTUAL
# ============================================================
def calcular_distancia_percentual(referencia, valor):
    if referencia == 0:
        return 0

    return ((referencia - valor) / referencia) * 100

# ============================================================
# SOMBRA INFERIOR
# ============================================================
def calcular_sombra_inferior(
    abertura,
    fechamento,
    minima
):
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
# ============================================================
def verificar_candle_positivo(
    abertura,
    fechamento,
    minima
):
    # Candle negativo ou neutro
    if fechamento <= abertura:
        return True

    # Candle positivo
    corpo = fechamento - abertura
    sombra_inferior = abertura - minima

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
# RETOMADA DO FECHAMENTO
#
# D = fechamento anterior - mínima anterior
#
# fechamento anterior - fechamento atual
# <= 10% de D
#
# Se o fechamento atual ultrapassar o fechamento anterior,
# também passa.
# ============================================================
def verificar_retomada_fechamento(
    fechamento_atual,
    fechamento_anterior,
    minima_anterior
):
    distancia_referencia = (
        fechamento_anterior
        -
        minima_anterior
    )

    if distancia_referencia <= 0:
        return False

    distancia_maxima_permitida = (
        distancia_referencia
        *
        (
            PERCENTUAL_MAXIMO_DISTANCIA_FECHAMENTO
            /
            100
        )
    )

    distancia_fechamento_atual = (
        fechamento_anterior
        -
        fechamento_atual
    )

    return (
        distancia_fechamento_atual
        <=
        distancia_maxima_permitida
    )

# ============================================================
# REMOVER TIMEZONE
# ============================================================
def remover_timezone(dados):
    dados = dados.copy()

    if getattr(
        dados.index,
        "tz",
        None
    ) is not None:

        dados.index = (
            dados.index
            .tz_localize(None)
        )

    return dados

# ============================================================
# BUSCAR CANDLES DO PERÍODO ESCOLHIDO
# ============================================================
@st.cache_data(
    ttl=1800,
    show_spinner=False
)
def buscar_candles_analise(
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

    # Busca meses suficientes para montar
    # também o trimestre anterior.
    data_inicio = (
        periodo_selecionado - 18
    ).start_time

    # Busca até depois do mês escolhido,
    # mas posteriormente eliminamos qualquer mês futuro.
    data_fim = (
        periodo_selecionado + 1
    ).start_time + pd.Timedelta(days=2)

    dados_mensais = yf.Ticker(
        ticker
    ).history(
        start=data_inicio.strftime(
            "%Y-%m-%d"
        ),
        end=data_fim.strftime(
            "%Y-%m-%d"
        ),
        interval="1mo",
        auto_adjust=False,
        actions=False
    )

    if dados_mensais.empty:
        return (
            None,
            None,
            "Sem dados no Yahoo Finance"
        )

    dados_mensais = remover_timezone(
        dados_mensais
    )

    dados_mensais = (
        dados_mensais.dropna(
            subset=[
                "Open",
                "High",
                "Low",
                "Close"
            ]
        )
    )

    if dados_mensais.empty:
        return (
            None,
            None,
            "Sem candles válidos"
        )

    # ========================================================
    # ELIMINAR MESES POSTERIORES AO PERÍODO ESCOLHIDO
    #
    # Importante para estudos históricos.
    # ========================================================
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
    # Selecionado = fevereiro/2026
    #
    # atual    = fevereiro/2026
    # anterior = janeiro/2026
    # ========================================================
    if tempo_grafico == "mensal":

        periodo_anterior = (
            periodo_selecionado - 1
        )

        linhas_atual = dados_mensais[
            periodos_mensais
            ==
            periodo_selecionado
        ]

        linhas_anterior = dados_mensais[
            periodos_mensais
            ==
            periodo_anterior
        ]

        if linhas_atual.empty:
            return (
                None,
                None,
                f"Sem dados para "
                f"{periodo_selecionado.strftime('%m/%Y')}"
            )

        if linhas_anterior.empty:
            return (
                None,
                None,
                f"Sem dados para "
                f"{periodo_anterior.strftime('%m/%Y')}"
            )

        candle_atual = (
            linhas_atual.iloc[-1]
        )

        candle_anterior = (
            linhas_anterior.iloc[-1]
        )

        return (
            candle_atual,
            candle_anterior,
            None
        )

    # ========================================================
    # TRIMESTRAL
    #
    # O trimestre atual é montado somente
    # até o mês escolhido.
    #
    # Exemplo:
    #
    # fevereiro/2026:
    #
    # trimestre atual = janeiro + fevereiro
    #
    # março NÃO é utilizado.
    #
    # trimestre anterior = outubro + novembro + dezembro/2025
    # ========================================================
    if tempo_grafico == "trimestral":

        dados_trimestrais = (
            dados_mensais
            .resample(
                "QS-JAN"
            )
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
            pd.DateOffset(
                months=3
            )
        )

        if (
            inicio_trimestre_atual
            not in
            dados_trimestrais.index
        ):
            return (
                None,
                None,
                "Sem dados para o "
                "trimestre selecionado"
            )

        if (
            inicio_trimestre_anterior
            not in
            dados_trimestrais.index
        ):
            return (
                None,
                None,
                "Sem dados para o "
                "trimestre anterior"
            )

        candle_atual = (
            dados_trimestrais.loc[
                inicio_trimestre_atual
            ]
        )

        candle_anterior = (
            dados_trimestrais.loc[
                inicio_trimestre_anterior
            ]
        )

        return (
            candle_atual,
            candle_anterior,
            None
        )

    return (
        None,
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
        candle_atual,
        candle_anterior,
        erro
    ) = buscar_candles_analise(
        ticker,
        tempo_grafico,
        ano,
        mes
    )

    if erro is not None:
        return False, erro

    # ========================================================
    # CANDLE ATUAL
    # ========================================================
    abertura_atual = float(
        candle_atual["Open"]
    )

    minima_atual = float(
        candle_atual["Low"]
    )

    fechamento_atual = float(
        candle_atual["Close"]
    )

    # ========================================================
    # CANDLE ANTERIOR
    # ========================================================
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
        or minima_atual <= 0
        or fechamento_atual <= 0
        or abertura_anterior <= 0
        or maxima_anterior <= 0
        or minima_anterior <= 0
        or fechamento_anterior <= 0
    ):
        return (
            False,
            "Preço inválido ou zerado"
        )

    # ========================================================
    # FILTRO 1
    #
    # Candle anterior negativo ou neutro = permitido
    #
    # Se positivo:
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
    # Sombra inferior anterior >= 25%
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
    # SEGUNDO FUNDO
    #
    # A mínima atual precisa atingir pelo menos
    # 80% da distância:
    #
    # fechamento anterior -> mínima anterior
    # ========================================================
    distancia_anterior = (
        calcular_distancia_percentual(
            fechamento_anterior,
            minima_anterior
        )
    )

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
    # RETOMADA
    #
    # D =
    # fechamento anterior - mínima anterior
    #
    # fechamento anterior - fechamento atual
    # <= 10% de D
    #
    # Se fechamento atual > fechamento anterior,
    # também passa.
    # ========================================================
    houve_retomada = (
        verificar_retomada_fechamento(
            fechamento_atual,
            fechamento_anterior,
            minima_anterior
        )
    )

    # ========================================================
    # FILTRO 5
    #
    # Abertura atual próxima
    # do fechamento anterior
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
        houve_retomada
        and
        abertura_dentro_limite
    )

    return passou, None

# ============================================================
# INTERFACE
# ============================================================
st.title(
    "📈 Varredura de Ativos B3"
)

st.write(
    "Busca por possível fundo duplo "
    "com retomada do preço."
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
# ESCOLHER MÊS E ANO
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
            list(
                MESES.keys()
            ),
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

periodo_selecionado = (
    pd.Period(
        year=ano_selecionado,
        month=mes_selecionado,
        freq="M"
    )
)

periodo_atual = (
    hoje.to_period("M")
)

# ============================================================
# MOSTRAR O QUE SERÁ COMPARADO
# ============================================================
if periodo_selecionado > periodo_atual:

    st.warning(
        "O período selecionado "
        "está no futuro."
    )

elif tempo_grafico == "mensal":

    periodo_anterior = (
        periodo_selecionado - 1
    )

    st.info(
        f"Candle anterior: "
        f"{periodo_anterior.strftime('%m/%Y')} "
        f" | "
        f"Candle analisado: "
        f"{periodo_selecionado.strftime('%m/%Y')}"
    )

else:

    numero_trimestre = (
        (
            mes_selecionado - 1
        )
        //
        3
    ) + 1

    st.info(
        f"Trimestre analisado: "
        f"{numero_trimestre}º trimestre "
        f"de {ano_selecionado}, "
        f"considerando dados somente "
        f"até {nome_mes_selecionado}/"
        f"{ano_selecionado}."
    )

# ============================================================
# ARQUIVO CSV
# ============================================================
st.subheader(
    "Lista de ativos"
)

arquivo_upload = (
    st.file_uploader(
        "Selecione o arquivo CSV",
        type=["csv"]
    )
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
        "1. Candle anterior negativo ou neutro "
        "é permitido. Se for positivo, o corpo "
        "deve representar no máximo 25% "
        "da sombra inferior."
    )

    st.write(
        "2. A sombra inferior do candle anterior "
        "deve representar pelo menos 25% "
        "da amplitude total."
    )

    st.write(
        "3. A mínima do período analisado deve "
        "atingir pelo menos 80% da distância "
        "entre o fechamento anterior "
        "e a mínima anterior."
    )

    st.write(
        "4. O fechamento do período analisado "
        "deve ficar a no máximo 10% da distância "
        "entre o fechamento anterior "
        "e a mínima anterior abaixo do "
        "fechamento anterior. "
        "Se ultrapassar o fechamento anterior, "
        "também passa."
    )

    st.write(
        "5. A distância entre a abertura "
        "do período analisado e o fechamento "
        "anterior não pode superar 15% "
        "da distância entre o fechamento "
        "anterior e a mínima anterior."
    )

    st.write(
        "No modo trimestral, o trimestre atual "
        "é calculado somente até o mês escolhido, "
        "para não utilizar meses futuros "
        "em estudos históricos."
    )

# ============================================================
# EXECUTAR ANÁLISE
# ============================================================
if st.button(
    "Executar análise",
    type="primary",
    use_container_width=True
):

    if (
        periodo_selecionado
        >
        periodo_atual
    ):

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
            f"Erro ao carregar CSV: "
            f"{erro}"
        )

        st.stop()

    ativos_encontrados = []
    erros = []

    total = len(
        tickers
    )

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

            passou, erro = (
                analisar_ativo(
                    ticker,
                    tempo_grafico,
                    ano_selecionado,
                    mes_selecionado
                )
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

        df_resultados = (
            pd.DataFrame({
                "Ativo":
                    ativos_encontrados
            })
        )

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
            "a todos os critérios."
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
