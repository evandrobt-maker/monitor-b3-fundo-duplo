import pandas as pd
import yfinance as yf

# ============================================================
# CONFIGURAÇÕES
# ============================================================

CAMINHO_CSV = r"IBOVDia_300925_sem_duplicadas_rev02.csv"

# FILTRO 1
# Se o candle anterior for positivo, o corpo pode representar
# no máximo 25% da sombra inferior.
PERCENTUAL_MAXIMO_CORPO_POSITIVO = 25.0

# FILTRO 2
# Sombra inferior mínima do candle anterior em relação
# à amplitude total máxima - mínima.
PERCENTUAL_MINIMO_SOMBRA = 25.0

# FILTRO 3
# A distância entre fechamento anterior e mínima atual
# deve representar pelo menos 80% da distância entre
# fechamento anterior e mínima anterior.
PERCENTUAL_MINIMO_REPETICAO = 80.0

# FILTRO 4
# A distância entre abertura atual e fechamento anterior
# não pode representar mais de 15% da distância entre
# fechamento anterior e mínima anterior.
PERCENTUAL_MAXIMO_DISTANCIA_ABERTURA = 15.0


# ============================================================
# ESCOLHER TEMPO GRÁFICO
# ============================================================

def escolher_tempo_grafico():
    while True:
        print()
        print("=" * 50)
        print("ESCOLHA O TEMPO GRÁFICO")
        print("=" * 50)
        print("1 - MENSAL")
        print("2 - TRIMESTRAL")
        print()
        escolha = input("Digite 1 ou 2: ").strip()

        if escolha == "1":
            return "mensal"
        elif escolha == "2":
            return "trimestral"
        else:
            print("Opção inválida. Digite apenas 1 ou 2.")


# ============================================================
# CARREGAR TICKERS DO CSV
# ============================================================

def carregar_tickers(caminho_csv):
    df = pd.read_csv(
        caminho_csv,
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

    distancia = ((referencia - valor) / referencia) * 100

    return distancia


# ============================================================
# CALCULAR TAMANHO DA SOMBRA INFERIOR
#
# CANDLE NEGATIVO:
# sombra = fechamento - mínima
#
# CANDLE POSITIVO:
# sombra = abertura - mínima
#
# Forma geral:
# menor valor entre abertura/fechamento - mínima
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
# CALCULAR PERCENTUAL DA SOMBRA INFERIOR
# EM RELAÇÃO À AMPLITUDE TOTAL DO CANDLE
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

    percentual = (
        sombra_inferior
        /
        amplitude_total
    ) * 100

    return percentual


# ============================================================
# FILTRO PARA CANDLE POSITIVO
#
# Se o candle for negativo ou neutro:
# passa neste filtro.
#
# Se for positivo:
#
# corpo = fechamento - abertura
# sombra inferior = abertura - mínima
#
# corpo deve representar no máximo 25%
# da sombra inferior.
# ============================================================

def verificar_candle_positivo(
    abertura,
    fechamento,
    minima
):
    # Candle negativo
    if fechamento < abertura:
        return True, 0

    # Candle neutro / doji
    if fechamento == abertura:
        return True, 0

    # Candle positivo
    corpo = fechamento - abertura
    sombra_inferior = abertura - minima

    # Candle positivo sem sombra inferior
    if sombra_inferior <= 0:
        return False, float("inf")

    percentual_corpo_sombra = (
        corpo
        /
        sombra_inferior
    ) * 100

    passou = (
        percentual_corpo_sombra
        <=
        PERCENTUAL_MAXIMO_CORPO_POSITIVO
    )

    return passou, percentual_corpo_sombra


# ============================================================
# CALCULAR DISTÂNCIA DA ABERTURA ATUAL
# EM RELAÇÃO AO FECHAMENTO ANTERIOR
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

    percentual = (
        distancia_abertura
        /
        distancia_fechamento_minima
    ) * 100

    return percentual


# ============================================================
# FORMATAÇÃO
# ============================================================

def formatar_preco(valor):
    return f"{valor:.2f}".replace(".", ",")


def formatar_percentual(valor):
    return f"{valor:.2f}%".replace(".", ",")


def formatar_volume(valor):
    return f"{int(valor):,}".replace(",", ".")


# ============================================================
# BUSCAR DADOS NO YAHOO FINANCE
# ============================================================

def buscar_dados(ticker, tempo_grafico):

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
    # T1 = janeiro + fevereiro + março
    # T2 = abril + maio + junho
    # T3 = julho + agosto + setembro
    # T4 = outubro + novembro + dezembro
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
        raise ValueError("Tempo gráfico inválido.")


# ============================================================
# PROGRAMA PRINCIPAL
# ============================================================

def main():

    # ========================================================
    # ESCOLHER TEMPO GRÁFICO
    # ========================================================

    tempo_grafico = escolher_tempo_grafico()

    print()
    print("=" * 80)
    print("VARREDURA DE ATIVOS B3")
    print("=" * 80)
    print(f"Tempo gráfico selecionado: {tempo_grafico.upper()}")
    print()

    # ========================================================
    # CARREGAR ATIVOS
    # ========================================================

    try:
        tickers = carregar_tickers(CAMINHO_CSV)

    except Exception as erro:
        print("ERRO AO CARREGAR CSV:")
        print(erro)
        return

    print(f"Total de ativos carregados: {len(tickers)}")
    print("Buscando dados no Yahoo Finance...")
    print()

    ativos_filtrados = []
    erros = []

    # ========================================================
    # ANALISAR CADA ATIVO
    # ========================================================

    for ticker in tickers:
        try:

            # =================================================
            # BUSCAR CANDLES
            # =================================================

            dados = buscar_dados(
                ticker,
                tempo_grafico
            )

            if dados.empty:
                erros.append(
                    (
                        ticker,
                        "Sem dados no Yahoo Finance"
                    )
                )
                continue

            dados = dados.dropna(
                subset=[
                    "Open",
                    "High",
                    "Low",
                    "Close"
                ]
            )

            if len(dados) < 2:
                erros.append(
                    (
                        ticker,
                        "Menos de dois candles disponíveis"
                    )
                )
                continue

            # =================================================
            # CANDLE ATUAL
            # =================================================

            candle_atual = dados.iloc[-1]

            abertura_atual = float(
                candle_atual["Open"]
            )

            maxima_atual = float(
                candle_atual["High"]
            )

            minima_atual = float(
                candle_atual["Low"]
            )

            fechamento_atual = float(
                candle_atual["Close"]
            )

            volume_atual = float(
                candle_atual["Volume"]
            )

            # =================================================
            # CANDLE ANTERIOR
            # =================================================

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

            volume_anterior = float(
                candle_anterior["Volume"]
            )

            # =================================================
            # EVITAR PREÇOS INVÁLIDOS
            # =================================================

            if (
                abertura_atual <= 0
                or abertura_anterior <= 0
                or fechamento_anterior <= 0
                or minima_anterior <= 0
                or minima_atual <= 0
                or maxima_anterior <= 0
            ):
                erros.append(
                    (
                        ticker,
                        "Preço inválido ou zerado"
                    )
                )
                continue

            # =================================================
            # FILTRO 1
            #
            # O CANDLE ANTERIOR PODE SER:
            #
            # NEGATIVO -> permitido
            #
            # POSITIVO -> corpo deve representar
            # no máximo 25% da sombra inferior.
            #
            # Corpo positivo:
            # fechamento - abertura
            #
            # Sombra inferior:
            # abertura - mínima
            # =================================================

            (
                formato_candle_valido,
                percentual_corpo_sombra
            ) = verificar_candle_positivo(
                abertura_anterior,
                fechamento_anterior,
                minima_anterior
            )

            # =================================================
            # FILTRO 2
            #
            # SOMBRA INFERIOR DO CANDLE ANTERIOR
            # DEVE REPRESENTAR PELO MENOS 25%
            # DA AMPLITUDE TOTAL DO CANDLE
            # =================================================

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

            # =================================================
            # FILTRO 3
            #
            # DISTÂNCIA ENTRE:
            #
            # fechamento anterior -> mínima anterior
            # =================================================

            distancia_anterior = (
                calcular_distancia_percentual(
                    fechamento_anterior,
                    minima_anterior
                )
            )

            # =================================================
            # DISTÂNCIA ENTRE:
            #
            # fechamento anterior -> mínima atual
            # =================================================

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

            if distancia_anterior > 0:
                percentual_atingido = (
                    distancia_minima_atual
                    /
                    distancia_anterior
                ) * 100
            else:
                percentual_atingido = 0

            # =================================================
            # FILTRO 4
            #
            # DISTÂNCIA ENTRE:
            #
            # abertura atual -> fechamento anterior
            #
            # NÃO PODE SER MAIOR QUE 15%
            # DA DISTÂNCIA:
            #
            # fechamento anterior -> mínima anterior
            # =================================================

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

            # =================================================
            # FILTRO FINAL
            # =================================================

            if (
                formato_candle_valido
                and sombra_minima_25
                and atingiu_80_porcento
                and abertura_dentro_limite
            ):

                ativos_filtrados.append({
                    "ticker": ticker,
                    "abertura_atual": abertura_atual,
                    "maxima_atual": maxima_atual,
                    "minima_atual": minima_atual,
                    "fechamento_atual": fechamento_atual,
                    "volume_atual": volume_atual,
                    "abertura_anterior": abertura_anterior,
                    "maxima_anterior": maxima_anterior,
                    "minima_anterior": minima_anterior,
                    "fechamento_anterior": fechamento_anterior,
                    "volume_anterior": volume_anterior,
                    "sombra_anterior": percentual_sombra_anterior,
                    "distancia_anterior": distancia_anterior,
                    "distancia_minima_atual": distancia_minima_atual,
                    "distancia_minima_exigida": distancia_minima_exigida,
                    "percentual_atingido": percentual_atingido,
                    "percentual_distancia_abertura":
                        percentual_distancia_abertura,
                    "percentual_corpo_sombra":
                        percentual_corpo_sombra
                })

        except Exception as erro:
            erros.append(
                (
                    ticker,
                    str(erro)
                )
            )

    # ========================================================
    # RESULTADOS
    # ========================================================

    print()
    print("=" * 80)
    print(
        f"ATIVOS QUE PASSARAM PELO FILTRO "
        f"- {tempo_grafico.upper()}"
    )
    print("=" * 80)

    if not ativos_filtrados:
        print("Nenhum ativo atendeu a todos os critérios.")
    else:
        for ativo in ativos_filtrados:
            print(f"ATIVO: {ativo['ticker']}")

    # ========================================================
    # RESUMO
    # ========================================================

    print()
    print("=" * 80)
    print("RESUMO")
    print("=" * 80)
    print(f"Tempo gráfico: {tempo_grafico.upper()}")
    print(f"Ativos analisados: {len(tickers)}")
    print(f"Ativos encontrados: {len(ativos_filtrados)}")
    print(f"Ativos ignorados/com erro: {len(erros)}")

    # ========================================================
    # MOSTRAR ERROS
    # ========================================================

    if erros:
        print()
        print("=" * 80)
        print("ATIVOS COM ERRO OU SEM DADOS")
        print("=" * 80)

        for ticker, motivo in erros:
            print(f"{ticker}: {motivo}")


# ============================================================
# EXECUTAR
# ============================================================

if __name__ == "__main__":
    main()