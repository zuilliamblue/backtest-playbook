import streamlit as st
import pandas as pd
from pathlib import Path
from datetime import datetime, date, time, timedelta
import math
import numpy as np
# locale foi removido - não precisamos mais dele

# --- Configura o idioma para Português (Brasil) ---
# Bloco removido - vamos fazer manualmente
# ...
# ...

# =========================================================
# FUNÇÕES DE FORMATAÇÃO (Reutilizáveis)
# =========================================================

def fmt_res(v):
    """Formata um número para o padrão R$ 1.234,00"""
    if pd.isna(v):
        return ""
    try:
        val = float(v)
        # Formato R$ com 2 casas decimais, trocando , por . e vice-versa
        return f"R$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (ValueError, TypeError):
        return str(v)

def color_res(v_str):
    """Cor baseada no valor (lê o formato R$ 1.234,00)"""
    if not isinstance(v_str, str) or not v_str.startswith("R$"):
        # Tenta converter direto se não for string R$ (para Exp Max Neg)
        try:
            val = float(v_str)
        except (ValueError, TypeError):
            return ""
    else:
        # Limpa a string 'R$ 1.234,00' para '1234.00'
        try:
            val = float(v_str.replace("R$ ", "").replace(".", "").replace(",", "."))
        except (ValueError, TypeError):
            return ""
            
    if val > 0:
        return "color: #22c55e; font-weight: 600;"  # verde
    elif val < 0:
        return "color: #ef4444; font-weight: 600;"  # vermelho
    else:
        return "color: #e5e7eb;" # Cinza claro (neutro)

def fmt_data(x):
    try:
        return pd.to_datetime(x).strftime("%d-%m-%Y")
    except Exception:
        return ""

def fmt_price(v):
    if pd.isna(v):
        return ""
    # 150590 -> "150.590"
    return f"{v:,.0f}".replace(",", ".")

def fmt_box(v):
    if pd.isna(v):
        return "" # <-- Mudado de "None" para ""
    return f"{int(v)}"  # só inteiro, sem casas decimais


# =========================================================
# Carregamento de dados do Playbook-20.xlsx
# =========================================================
@st.cache_data
def load_playbook_data():
    base_path = Path(__file__).resolve().parent

    possible_paths = [
        base_path / "Playbook-20.xlsx",
        base_path.parent / "Playbook-20.xlsx",
        base_path / "data" / "Playbook-20.xlsx",
    ]

    excel_path = None
    for p in possible_paths:
        if p.exists():
            excel_path = p
            break

    if excel_path is None:
        raise FileNotFoundError(
            "Não encontrei o arquivo 'Playbook-20.xlsx' nas pastas padrão. "
            "Coloque o arquivo na mesma pasta do Playbook.py ou em uma pasta 'data'."
        )

    df_geral = pd.read_excel(excel_path, sheet_name="Geral")
    df_indicadores = pd.read_excel(excel_path, sheet_name="Indicadores")

    # Tipos básicos
    df_geral["Data"] = pd.to_datetime(df_geral["Data"]).dt.date
    df_geral["Hora"] = pd.to_datetime(df_geral["Hora"].astype(str)).dt.time
    df_indicadores["Dia"] = pd.to_datetime(df_indicadores["Dia"]).dt.date

    return df_geral, df_indicadores


# =========================================================
# Lógica operacional do Playbook (tabela)
# =========================================================
def build_playbook_table(
    df_geral,
    df_ind,
    data_inicio=None,
    data_fim=None,
    hora_fim=time(17, 45),
    alvos_config=None,
    pts_stop=350,
):
    if alvos_config is None or len(alvos_config) == 0:
        alvos_config = [{"alvo": 1, "alvo_pts": 0, "qtd": 1}]

    df = df_geral.copy()
    ind = df_ind.copy()

    # Garantir tipos
    df["Data"] = pd.to_datetime(df["Data"]).dt.date
    df["Hora"] = pd.to_datetime(df["Hora"].astype(str)).dt.time
    ind["Dia"] = pd.to_datetime(ind["Dia"]).dt.date

    # Renomeia colunas de indicadores para facilitar
    ind = ind.rename(
        columns={
            "Dia": "Data",
            "Mínima Injusta": "MinInj",
            "Máxima Injusta": "MaxInj",
        }
    )

    # Junta os indicadores no dia
    df = df.merge(ind, on="Data", how="left")

    # Ordena
    df = df.sort_values(["Data", "Box"]).reset_index(drop=True)

    # Filtro de datas
    if data_inicio is not None:
        df = df[df["Data"] >= data_inicio]
    if data_fim is not None:
        df = df[df["Data"] <= data_fim]

    # Filtro de hora fim
    df = df[df["Hora"] <= hora_fim].copy()

    if df.empty:
        return pd.DataFrame()

    # Abertura do dia = primeiro Abert do dia
    df["AbertDia"] = df.groupby("Data")["Abert"].transform("first")

    # Lado do box (só informativo, pelo candle)
    df["Lado"] = np.where(
        df["Fec"] > df["Abert"],
        "Alta",
        np.where(df["Fec"] < df["Abert"], "Baixa", "Neutro"),
    )

    linhas_saida = []

    # Loop dia a dia
    for data_dia, df_day in df.groupby("Data"):
        df_day = df_day.sort_values("Box").reset_index(drop=True)

        # Box 1
        row_box1 = df_day[df_day["Box"] == 1]
        if row_box1.empty:
            row_box1 = df_day.iloc[[0]]
        row_box1 = row_box1.iloc[0]

        vah = float(row_box1["VAH"]) if not pd.isna(row_box1["VAH"]) else math.nan
        val = float(row_box1["VAL"]) if not pd.isna(row_box1["VAL"]) else math.nan
        min_inj = (
            float(row_box1["MinInj"]) if not pd.isna(row_box1["MinInj"]) else math.nan
        )
        max_inj = (
            float(row_box1["MaxInj"]) if not pd.isna(row_box1["MaxInj"]) else math.nan
        )
        abrir = float(row_box1["Abert"])
        abert_dia = float(row_box1["AbertDia"])

        # ----------------------------------
        # Cenário (1 a 5) com base na abertura do Box 1 (LÓGICA ATUALIZADA)
        # ----------------------------------
        
        # 4) Abrir abaixo ou NA Min Injusta (Sua regra: Abertura <= Min)
        if not math.isnan(min_inj) and abrir <= min_inj:
            cenario = 4
            
        # 5) Abrir acima ou NA Max Injusta (Sua regra: Abertura >= max)
        elif not math.isnan(max_inj) and abrir >= max_inj:
            cenario = 5
            
        # 1) Abrir entre VAL e VAH (Inclusivo)
        elif not math.isnan(val) and not math.isnan(vah) and val <= abrir <= vah:
            cenario = 1
            
        # 2) Abrir entre Min Injusta (Exclusivo) e VAL (Exclusivo)
        elif (
            not math.isnan(val)
            and not math.isnan(min_inj)
            and min_inj < abrir < val # (Sua regra: > Min e < VAL)
        ):
            cenario = 2
            
        # 3) Abrir entre VAH (Exclusivo) e Max Injusta (Exclusivo)
        elif (
            not math.isnan(vah)
            and not math.isnan(max_inj)
            and vah < abrir < max_inj # (Sua regra: > VAH e < Max)
        ):
            cenario = 3
            
        else:
            cenario = 0  # sem cenário definido

        # ----------------------------------
        # Entrada
        # ----------------------------------
        entrada = ""
        entrada_box = None
        entrada_row = None
        entrada_price = None
        not_found_flag = False

        if cenario == 1:
            # Busca VAH/VAL a partir do box seguinte até o final do dia
            df_after = df_day[df_day["Box"] > row_box1["Box"]]

            # VAL -> Compra se bater primeiro
            if not math.isnan(val):
                cond_val = df_after["Mínima"] <= val
                idx_val = df_after[cond_val].index.min()
                box_val = (
                    int(df_after.loc[idx_val, "Box"])
                    if pd.notna(idx_val) # <-- CORRIGIDO AQUI
                    else None
                )
            else:
                box_val = None

            # VAH -> Venda se bater primeiro
            if not math.isnan(vah):
                cond_vah = df_after["Máxima"] >= vah
                idx_vah = df_after[cond_vah].index.min()
                box_vah = (
                    int(df_after.loc[idx_vah, "Box"])
                    if pd.notna(idx_vah) # <-- CORRIGIDO AQUI
                    else None
                )
            else:
                box_vah = None

            if box_val is None and box_vah is None:
                # Não pegou nem VAL nem VAH no dia
                not_found_flag = True
            else:
                # O menor box do dia decide quem veio primeiro
                if box_val is not None and (box_vah is None or box_val < box_vah):
                    entrada = "Compra"
                    entrada_box = box_val
                    entrada_row = df_after[df_after["Box"] == box_val].iloc[0]
                elif box_vah is not None and (box_val is None or box_vah < box_val):
                    entrada = "Venda"
                    entrada_box = box_vah
                    entrada_row = df_after[df_after["Box"] == box_vah].iloc[0]
                else:
                    # Empate ou algo esquisito -> trata como não encontrado
                    not_found_flag = True

            if not_found_flag:
                entrada = "Não encontrado"
                entrada_box = int(row_box1["Box"])
                entrada_row = row_box1

        # Cenário 2 e 5: BuyAtMarket no Box 1
        elif cenario in (2, 5):
            entrada = "Compra"
            entrada_box = int(row_box1["Box"])
            entrada_row = row_box1

        # Cenário 3 e 4: SellShortAtMarket no Box 1
        elif cenario in (3, 4):
            entrada = "Venda"
            entrada_box = int(row_box1["Box"])
            entrada_row = row_box1

        else:
            # Sem cenário válido
            entrada = ""
            entrada_box = int(row_box1["Box"])
            entrada_row = row_box1

        # Preço de referência da entrada
        if entrada_row is not None:
            if entrada_box == 1:
                # Box 1 usa abertura do dia
                entrada_price = float(entrada_row["Abert"])
            else:
                # Demais boxes usam fechamento do box da entrada
                entrada_price = float(entrada_row["Fec"])

        # ----------------------------------
        # Stop e Alvos
        # ----------------------------------
        df_after_entry = (
            df_day[df_day["Box"] > entrada_box]
            if entrada_box is not None
            else df_day.iloc[0:0]
        )

        stop_box = None
        stop_price = None
        valor_ponto = 0.2  # fixo por enquanto

        # Stop único (para todos os alvos)
        if entrada in ("Compra", "Venda") and entrada_price is not None:
            if entrada == "Compra":
                if entrada_box == 1:
                    stop_price = entrada_row["Abert"] - pts_stop
                else:
                    stop_price = entrada_row["Fec"] - pts_stop
                cond_stop = df_after_entry["Fec"] <= stop_price
            else:  # Venda
                if entrada_box == 1:
                    stop_price = entrada_row["Abert"] + pts_stop
                else:
                    stop_price = entrada_row["Fec"] + pts_stop
                cond_stop = df_after_entry["Fec"] >= stop_price

            idx_stop = df_after_entry[cond_stop].index.min()
            if isinstance(idx_stop, (int, np.integer)):
                stop_box = int(df_after_entry.loc[idx_stop, "Box"])

        alvo_boxes = {}
        resultados = []

        for idx_alvo, cfg in enumerate(alvos_config, start=1):
            pts = cfg.get("alvo_pts", 0)
            qtd = cfg.get("qtd", 1)

            if entrada not in ("Compra", "Venda") or entrada_price is None or pts <= 0:
                alvo_box = None
                res = 0.0
            else:
                if entrada == "Compra":
                    # Compra: alvo acima do preço de entrada
                    if entrada_box == 1:
                        target_price = entrada_row["Abert"] + pts
                    else:
                        target_price = entrada_row["Fec"] + pts
                    cond_target = df_after_entry["Fec"] >= target_price
                else:  # Venda
                    # Venda: alvo abaixo do preço de entrada
                    if entrada_box == 1:
                        target_price = entrada_row["Abert"] - pts
                    else:
                        target_price = entrada_row["Fec"] - pts
                    cond_target = df_after_entry["Fec"] <= target_price

                idx_target = df_after_entry[cond_target].index.min()
                if isinstance(idx_target, (int, np.integer)):
                    alvo_box = int(df_after_entry.loc[idx_target, "Box"])
                else:
                    alvo_box = None

                # Quem veio primeiro: alvo ou stop
                if alvo_box is None and stop_box is None:
                    res = 0.0
                elif alvo_box is not None and (stop_box is None or alvo_box < stop_box):
                    # Alvo ganhou
                    res = pts * valor_ponto * qtd
                else:
                    # Stop ganhou
                    res = -pts_stop * valor_ponto * qtd

            alvo_boxes[idx_alvo] = alvo_box
            resultados.append(res)

        resultado_total = float(sum(resultados))

        # ----------------------------------
        # Monta a linha de saída (1 linha por dia / por operação)
        # ----------------------------------
        linha = {
            "Data": entrada_row["Data"],
            "Hora": entrada_row["Hora"],
            "Abert": entrada_row["Abert"],
            "Máxima": entrada_row["Máxima"],
            "Mínima": entrada_row["Mínima"],
            "Fech": entrada_row["Fec"],
            "Box": entrada_row["Box"],
            "Abert. Dia": abert_dia,
            "VAH": vah,
            "VAL": val,
            "Max Inj": max_inj,
            "Min Inj": min_inj,
            "Lado": entrada_row["Lado"],
            "Cenário": cenario,
            "Entrada": entrada,
        }

        # Colunas dos Alvos (Alvo-1, Alvo-2, ...)
        for i in range(1, len(alvos_config) + 1):
            linha[f"Alvo-{i}"] = alvo_boxes.get(i)

        # Coluna Stop (box do stop, se houver)
        linha["Stop"] = stop_box

        # Colunas Add (Add-1, Add-2, ...)
        for i, cfg in enumerate(alvos_config, start=1):
            qtd = cfg.get("qtd", 1)
            linha[f"Add-{i}"] = qtd if entrada in ("Compra", "Venda") else 0

        # Colunas de resultado (Res-1, Res-2, ...)
        for i, res in enumerate(resultados, start=1):
            linha[f"Res-{i}"] = res

        # Resultado Total
        linha["Resultado Total"] = resultado_total

        linhas_saida.append(linha)

    if not linhas_saida:
        return pd.DataFrame()

    resultado_df = pd.DataFrame(linhas_saida)

    # Garante a ordem das colunas pedida
    cols_base = [
        "Data",
        "Hora",
        "Abert",
        "Máxima",
        "Mínima",
        "Fech",
        "Box",
        "Abert. Dia",
        "VAH",
        "VAL",
        "Max Inj",
        "Min Inj",
        "Lado",
        "Cenário",
        "Entrada",
    ]
    cols_alvo = [f"Alvo-{i}" for i in range(1, len(alvos_config) + 1)]
    cols_stop = ["Stop"]
    cols_add = [f"Add-{i}" for i in range(1, len(alvos_config) + 1)]
    cols_res = [f"Res-{i}" for i in range(1, len(alvos_config) + 1)]
    cols_total = ["Resultado Total"]
    
    cols = cols_base + cols_alvo + cols_stop + cols_add + cols_res + cols_total

    # Filtra colunas para garantir que só existam as que estão no DF
    cols_existentes = [c for c in cols if c in resultado_df.columns]
    resultado_df = resultado_df[cols_existentes]


    # --- CÁLCULO DO ACUMULADO MENSAL (Dia-Dia) ---
    # A tabela PRECISA ser ordenada por data (antigo -> novo) ANTES do cumsum
    if "Resultado Total" in resultado_df.columns:
        # 1. Garante data como datetime
        resultado_df["Data"] = pd.to_datetime(resultado_df["Data"])
        
        # 2. Ordena (Mais antigo primeiro) para o CÁLCULO
        resultado_df = resultado_df.sort_values(by=["Data", "Hora"], ascending=True)
        
        # 3. Cria o grupo do Mês/Ano
        resultado_df["MesAno"] = resultado_df["Data"].dt.to_period("M")
        
        # 4. Calcula o cumsum (soma acumulada) DENTRO de cada grupo
        resultado_df["Dia-Dia"] = resultado_df.groupby("MesAno")["Resultado Total"].cumsum()
        
        # 5. Remove a coluna auxiliar
        resultado_df = resultado_df.drop(columns=["MesAno"])
        
        # 6. Reorganiza colunas para colocar "Dia-Dia" após "Resultado Total"
        # (cols_existentes foi definido antes, ainda é válido)
        cols_finais = cols_existentes.copy()
        if "Resultado Total" in cols_finais:
            idx_total = cols_finais.index("Resultado Total")
            # Insere 'Dia-Dia' se ela não estiver lá por algum motivo
            if 'Dia-Dia' not in cols_finais:
                cols_finais.insert(idx_total + 1, "Dia-Dia")
        
        # Garante que não haja duplicatas
        cols_finais_unicas = []
        for col in cols_finais:
            if col not in cols_finais_unicas:
                cols_finais_unicas.append(col)
        
        # Garante que a nova coluna 'Dia-Dia' esteja presente se foi criada
        if 'Dia-Dia' not in cols_finais_unicas and 'Dia-Dia' in resultado_df.columns:
            if "Resultado Total" in cols_finais_unicas:
                idx_total = cols_finais_unicas.index("Resultado Total")
                cols_finais_unicas.insert(idx_total + 1, 'Dia-Dia')
            else:
                cols_finais_unicas.append('Dia-Dia')
        
        # Filtra apenas as colunas que realmente existem
        cols_finais_existentes = [c for c in cols_finais_unicas if c in resultado_df.columns]
        
        resultado_df = resultado_df[cols_finais_existentes]


    # Ordena do dia mais recente para o mais antigo (PARA EXIBIÇÃO)
    resultado_df = resultado_df.sort_values(
        ["Data", "Hora"], ascending=[False, False]
    ).reset_index(drop=True)

    return resultado_df


def format_playbook_table_for_display(tabela: pd.DataFrame):
    df = tabela.copy()

    # Garante índice simples
    df = df.reset_index(drop=True)

    # --- Colunas de preço / níveis (com ponto na milhar) ---
    price_cols = [
        "Abert",
        "Máxima",
        "Mínima",
        "Fech",
        "Abert. Dia",
        "VAH",
        "VAL",
        "Max Inj",
        "Min Inj",
    ]
    for col in price_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # --- Colunas de box (Alvo-x e Stop) -> inteiros sem .0000 ---
    box_cols = [c for c in df.columns if c.startswith("Alvo-")]
    if "Stop" in df.columns:
        box_cols.append("Stop")
    for col in box_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # --- Colunas de resultado (Res-x + Resultado Total + Dia-Dia) ---
    res_cols = [c for c in df.columns if c.startswith("Res-")]
    if "Resultado Total" in df.columns:
        res_cols.append("Resultado Total")
    if "Dia-Dia" in df.columns:
        res_cols.append("Dia-Dia")
        
    for col in res_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # ============================
    # Funções de formatação (Internas, pois são as globais)
    # ============================
    def color_lado(v):
        if v == "Alta":
            return "color: #22c55e;"  # verde
        elif v == "Baixa":
            return "color: #ef4444;"  # vermelho
        else:
            return "color: #e5e7eb;"

    def color_entrada(v):
        if v == "Compra":
            return "color: #3b82f6;"  # azul
        elif v == "Venda":
            return "color: #d946ef;"  # fuchsia (magenta/rosa)
        else:
            return "color: #e5e7eb;"

    # ============================
    # Monta Styler
    # ============================
    styler = df.style

    # Dicionário de formatos
    fmt_dict = {}

    if "Data" in df.columns:
        fmt_dict["Data"] = fmt_data

    for col in price_cols:
        if col in df.columns:
            fmt_dict[col] = fmt_price

    for col in box_cols:
        if col in df.columns:
            fmt_dict[col] = fmt_box

    for col in res_cols:
        if col in df.columns:
            fmt_dict[col] = fmt_res # Usa a formatação global R$

    styler = styler.format(fmt_dict, na_rep="") # <-- None vira ""

    # Cores da coluna Lado
    if "Lado" in df.columns:
        styler = styler.map(color_lado, subset=["Lado"])

    # Cores da coluna Entrada
    if "Entrada" in df.columns:
        styler = styler.map(color_entrada, subset=["Entrada"])

    # Cores das colunas de resultado (Usa a formatação global)
    if res_cols:
        # Filtra apenas colunas que realmente existem no DF
        res_cols_existentes = [c for c in res_cols if c in df.columns]
        if res_cols_existentes:
            styler = styler.map(color_res, subset=res_cols_existentes)
    
    # Esconde a coluna de índice (0, 1, 2...)
    styler = styler.hide(axis="index")

    # Converte o Styler para HTML
    # (Não usamos to_html() aqui, pois o st.markdown vai fazer isso)
    return styler.to_html(escape=False)



# =========================================================
# Página Playbook
# =========================================================
def pagina_playbook():
    st.set_page_config(layout="wide") # <-- Garante que a página use a largura total
    
    st.title("Playbook - Gabriel Pinotti")

    # Cards de resumo dos cenários – 3 em cima, 2 embaixo
    col1, col2, col3 = st.columns(3)

    # Cenário 1 – Azul
    with col1:
        st.markdown(
            """
            <div style="
                background-color: #0b1120;
                border-radius: 0.75rem;
                border: 1px solid #3b82f6;
                padding: 1rem 1.25rem;
                margin-top: 0.75rem;
            ">
              <h4 style="margin: 0 0 0.5rem 0; color: #bfdbfe;">Cenário 1</h4>
              <p style="margin: 0; line-height: 1.5; font-size: 0.9rem;">
                Abertura entre <b>VAL</b> ou <b>VAH</b>.<br>
                Compra na <b>VAL</b> e Venda na <b>VAH</b><br>
              </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Cenário 2 – Verde
    with col2:
        st.markdown(
            """
            <div style="
                background-color: #0b1120;
                border-radius: 0.75rem;
                border: 1px solid #22c55e;
                padding: 1rem 1.25rem;
                margin-top: 0.75rem;
            ">
              <h4 style="margin: 0 0 0.5rem 0; color: #bbf7d0;">Cenário 2</h4>
              <p style="margin: 0; line-height: 1.5; font-size: 0.9rem;">
                Abertura entre <b>VAL</b> e <b>Min Injusta</b>.<br>
                Entrada: <b>Compra a Mercado</b>.
              </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Cenário 3 – Laranja
    with col3:
        st.markdown(
            """
            <div style="
                background-color: #0b1120;
                border-radius: 0.75rem;
                border: 1px solid #f97316;
                padding: 1rem 1.25rem;
                margin-top: 0.75rem;
            ">
              <h4 style="margin: 0 0 0.5rem 0; color: #fed7aa;">Cenário 3</h4>
              <p style="margin: 0; line-height: 1.5; font-size: 0.9rem;">
                Abertura entre <b>VAH</b> e <b>Max Injusta</b>.<br>
                Entrada: <b>Venda a Mercado</b>.
              </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Segunda linha: 2 cards centralizados (Amarelo e Purple)
    col4, col5, col6 = st.columns(3)

    # Cenário 4 – Amarelo
    with col4:
        st.markdown(
            """
            <div style="
                background-color: #0b1120;
                border-radius: 0.75rem;
                border: 1px solid #eab308;
                padding: 1rem 1.25rem;
                margin-top: 0.75rem;
            ">
              <h4 style="margin: 0 0 0.5rem 0; color: #facc15;">Cenário 4</h4>
              <p style="margin: 0; line-height: 1.5; font-size: 0.9rem;">
                Abertura <b>abaixo</b> da <b>Min Injusta</b>.<br>
                Entrada: <b>Venda a Mercado</b>.
              </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Cenário 5 – Purple
    with col5:
        st.markdown(
            """
            <div style="
                background-color: #0b1120;
                border-radius: 0.75rem;
                border: 1px solid #a855f7;
                padding: 1rem 1.25rem;
                margin-top: 0.75rem;
            ">
              <h4 style="margin: 0 0 0.5rem 0; color: #e9d5ff;">Cenário 5</h4>
              <p style="margin: 0; line-height: 1.5; font-size: 0.9rem;">
                Abertura <b>acima</b> da <b>Max Injusta</b>.<br>
                Entrada: <b>Compra a Mercado</b>.
              </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # col6 fica vazio só para alinhar visualmente (3 em cima, 2 em cima)

    # CSS para centralizar tabelas e controlar o scroll
    st.markdown(
        """
        <style>
        
        /* O container base da tabela */
        .tabela-container {
            width: 100%;
            border-collapse: collapse; /* Para o HTML funcionar como o st.dataframe */
        }

        /* MODIFICADOR: Adiciona scroll APENAS se a classe .com-scroll estiver presente */
        .tabela-container.com-scroll {
            max-height: 700px; /* Altura da primeira tabela */
            overflow-y: auto;
            display: block; /* Necessário para o max-height funcionar */
        }

        /* Estilos da Tabela (Cabeçalho) */
        .tabela-container th {
            text-align: center !important;
            padding: 8px 12px;
            background-color: #1a202c; /* Fundo do cabeçalho (escuro) */
            color: #cbd5e1; /* Texto do cabeçalho (cinza claro) */
            border: 1px solid #2d3748;
            position: sticky; /* Cabeçalho gruda no topo */
            top: 0;
            z-index: 1;
        }

        /* Estilos da Tabela (Células) */
        .tabela-container td {
            text-align: center !important;
            padding: 8px 12px;
            border: 1px solid #2d3748; /* Borda da célula (cinza escuro) */
            color: #e5e7eb; /* Texto da célula (cinza claro) */
            white-space: nowrap; /* Impede quebra de linha */
        }
        
        /* Cor de fundo das linhas alternadas (zebra) */
        .tabela-container tbody tr:nth-child(even) {
            background-color: #1f2937; /* Fundo da linha par (um pouco mais claro) */
        }
        .tabela-container tbody tr:nth-child(odd) {
            background-color: #111827; /* Fundo da linha ímpar (escuro) */
        }

        </style>
        """,
        unsafe_allow_html=True,
    )


    # ---------------------------
    # Carrega dados
    # ---------------------------
    try:
        df_geral, df_indicadores = load_playbook_data()
    except FileNotFoundError as e:
        st.error(str(e))
        return

    # Limites de datas com base na aba Geral
    min_data = df_geral["Data"].min()
    max_data = df_geral["Data"].max()

    # ---------------------------
    # BLOCO DE FILTROS (sidebar)
    # ---------------------------
    st.sidebar.header("Filtros")

    data_inicio = st.sidebar.date_input(
        "Data de Início",
        value=min_data,
        min_value=min_data,
        max_value=max_data,
        format="DD/MM/YYYY", # <-- Formato PT-BR
    )

    data_fim = st.sidebar.date_input(
        "Data de Fim",
        value=max_data,  # dia mais recente
        min_value=min_data,
        max_value=max_data,
        format="DD/MM/YYYY", # <-- Formato PT-BR
    )

    # Hora fim: 12:00 até 18:00 a cada 15 minutos
    hora_opcoes = []
    current_dt = datetime.combine(date.today(), time(12, 0))
    end_dt = datetime.combine(date.today(), time(18, 0))
    while current_dt <= end_dt:
        hora_opcoes.append(current_dt.strftime("%H:%M"))
        current_dt += timedelta(minutes=15)

    hora_fim_str = st.sidebar.selectbox(
        "Hora Fim",
        options=hora_opcoes,
        index=hora_opcoes.index("17:45"),
    )

    # Qtde de Alvos
    qtde_alvos = st.sidebar.number_input(
        "Qtde. Alvos",
        min_value=1,
        max_value=10,
        value=1,
        step=1,
    )

    st.sidebar.markdown("---")
    alvos_config = []

    for i in range(1, qtde_alvos + 1):
        st.sidebar.markdown(f"**Alvo {i}**")

        alvo_pts = st.sidebar.number_input(
            f"Alvo {i} (pts)",
            min_value=0,
            step=50,
            value=700,
            key=f"alvo_{i}_pts",
        )

        qtd_contratos = st.sidebar.number_input(
            f"Qtde {i}",
            min_value=1,
            step=1,
            value=1,
            key=f"alvo_{i}_qtd",
        )

        alvos_config.append(
            {"alvo": i, "alvo_pts": alvo_pts, "qtd": qtd_contratos}
        )

    st.sidebar.markdown("---")
    pts_stop = st.sidebar.number_input(
        "Pts. Stop",
        min_value=50,
        max_value=5000,
        step=50,
        value=350,
    )

    # Botão Gerar Estatística
    st.sidebar.markdown("---")
    gerar_estatistica = st.sidebar.button("Gerar Estatística")

    # Estado: se já foi gerada alguma vez
    if "playbook_gerado" not in st.session_state:
        st.session_state["playbook_gerado"] = False
    if gerar_estatistica:
        st.session_state["playbook_gerado"] = True

    # ---------------------------
    # Mostrar/Ocultar Tabela + linha divisória
    # ---------------------------
    st.markdown("---") # Linha divisória acima do botão

    # Estado inicial do botão
    if "mostrar_tabela_playbook" not in st.session_state:
        st.session_state["mostrar_tabela_playbook"] = True # Começa visível

    # Define o texto do botão ANTES de desenhar
    if st.session_state["mostrar_tabela_playbook"]:
        texto_botao = "Ocultar Tabela"
    else:
        texto_botao = "Mostrar Tabela"

    if st.button(texto_botao):
        # Inverte o estado
        st.session_state["mostrar_tabela_playbook"] = (
            not st.session_state["mostrar_tabela_playbook"]
        )
        # Força o re-run imediato para o botão atualizar o texto
        st.rerun()

    # NÃO HÁ MAIS LINHA DIVISÓRIA AQUI


    # ---------------------------
    # Geração da tabela de Playbook
    # ---------------------------
    if st.session_state["playbook_gerado"]:
        hora_fim = datetime.strptime(hora_fim_str, "%H:%M").time()

        tabela = build_playbook_table(
            df_geral=df_geral,
            df_ind=df_indicadores,
            data_inicio=data_inicio,
            data_fim=data_fim,
            hora_fim=hora_fim,
            alvos_config=alvos_config,
            pts_stop=int(pts_stop),
        )

        if tabela.empty:
            st.warning("Nenhum dado encontrado para os filtros selecionados.")
            return # Para a execução se não houver dados
        
        # ---------------------------
        # Exibição da Tabela Playbook
        # ---------------------------
        if st.session_state["mostrar_tabela_playbook"]:
            st.subheader("Tabela Playbook - Operações por Dia")

            # Formata a tabela (Pandas Styler) e converte para HTML
            html_playbook = format_playbook_table_for_display(tabela)

            # Usa o container de Tabela com a classe .com-scroll
            st.markdown(
                f'<div class="tabela-container com-scroll">{html_playbook}</div>',
                unsafe_allow_html=True,
            )
        else:
            st.info(
                "Tabela Playbook está oculta. "
                "Clique em 'Mostrar Tabela' para exibir."
            )

        # =========================================================
        # NOVA SEÇÃO: Resultado Mensal
        # =========================================================
        
        st.markdown("---") # Linha divisória

        # Estado inicial do botão
        if "mostrar_tabela_mensal" not in st.session_state:
            st.session_state["mostrar_tabela_mensal"] = True # Começa visível

        # Define o texto do botão ANTES de desenhar
        if st.session_state["mostrar_tabela_mensal"]:
            
            # --- Cria colunas para as tabelas de resumo ---
            col_mensal, col_stats = st.columns([3, 2]) # 3 partes para mensal, 2 para stats

            with col_mensal:
                st.subheader("Resultado Mensal")
                
                # 1. Preparar dados para agrupar
                tabela_agg = tabela.copy()
                # Garante que 'Data' é datetime para agrupar
                tabela_agg['Data'] = pd.to_datetime(tabela_agg['Data'])
                
                # 2. Agrupar por Mês (usando 'Period' para ordenar)
                tabela_agg['MesAno'] = tabela_agg['Data'].dt.to_period('M')
                
                # 3. Calcular agregados (Soma do Resultado e Mínimo do Dia-Dia)
                # (Usamos .copy() para evitar o aviso SettingWithCopyWarning)
                tabela_agg_grouped = tabela_agg.groupby('MesAno').agg(
                    **{'Resultado Total': ('Resultado Total', 'sum'),
                       'Exp Max Neg': ('Dia-Dia', 'min')} # Pega o menor valor do 'Dia-Dia' no mês
                ).reset_index()
                
                # 4. Ordenar (Period objects ordenam corretamente por data)
                resultado_mensal_df = tabela_agg_grouped.sort_values('MesAno', ascending=False) # Mais recente primeiro
                
                # 5. Formatar o nome do Mês em PT-BR (Ex: Janeiro 2024)
                # (Substituído o strftime(%B) para evitar erros de encoding "MarÃ§o")
                
                mes_map = {
                    1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril', 
                    5: 'Maio', 6: 'Junho', 7: 'Julho', 8: 'Agosto', 
                    9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'
                }
                
                # Pega o número do mês (ex: 3)
                mes_num = resultado_mensal_df['MesAno'].dt.month
                # Pega o ano (ex: 2025)
                ano_num = resultado_mensal_df['MesAno'].dt.year
                
                # Mapeia e combina (ex: "Março 2025")
                resultado_mensal_df['Mês'] = mes_num.map(mes_map) + " " + ano_num.astype(str)
                
                # 6. Selecionar colunas finais
                resultado_mensal_df = resultado_mensal_df[['Mês', 'Resultado Total', 'Exp Max Neg']]

                # 7. Aplicar formatação (Styler)
                styler_mensal = resultado_mensal_df.style
                
                # Formata R$ e Colore
                styler_mensal = styler_mensal.format({
                    'Resultado Total': fmt_res,
                    'Exp Max Neg': fmt_res
                })
                styler_mensal = styler_mensal.map(
                    color_res, 
                    subset=['Resultado Total', 'Exp Max Neg']
                )
                
                # Esconde índice
                styler_mensal = styler_mensal.hide(axis="index")
                
                # Converte para HTML
                html_mensal = styler_mensal.to_html(escape=False)

                # Usa o container de Tabela SEM a classe .com-scroll
                st.markdown(
                    f'<div class="tabela-container">{html_mensal}</div>',
                    unsafe_allow_html=True,
                )
            
            with col_stats:
                st.subheader("Resumo por Período")
                
                # --- Prepara dados (usa o mesmo 'tabela_agg' da col_mensal) ---
                if 'tabela_agg' not in locals(): # Segurança se a outra falhar
                    tabela_agg = tabela.copy()
                    tabela_agg['Data'] = pd.to_datetime(tabela_agg['Data'])
                
                # --- 1. Tabela por Dia da Semana ---
                tabela_agg['DiaSemana'] = tabela_agg['Data'].dt.dayofweek
                dias_semana_map = {0: 'Seg', 1: 'Ter', 2: 'Qua', 3: 'Qui', 4: 'Sex'}
                
                # Filtra apenas dias de semana (0=Seg, 4=Sex)
                df_dias = tabela_agg[tabela_agg['DiaSemana'].isin(dias_semana_map.keys())].copy()
                
                if not df_dias.empty:
                    soma_dias = df_dias.groupby('DiaSemana')['Resultado Total'].sum()
                    # Garante que todos os dias da semana apareçam, mesmo com 0
                    soma_dias = soma_dias.reindex(dias_semana_map.keys(), fill_value=0)
                    soma_dias.index = soma_dias.index.map(dias_semana_map)
                    
                    # Transpõe para ficar horizontal (Seg, Ter... como colunas)
                    df_dias_final = pd.DataFrame(soma_dias).T
                    df_dias_final.index = ["Resultado"] # Renomeia o índice

                    styler_dias = df_dias_final.style.format(fmt_res).map(color_res)
                    styler_dias = styler_dias.hide(axis="index") # Esconde "Resultado"
                    html_dias = styler_dias.to_html(escape=False)
                    
                    st.markdown(
                        f'<div class="tabela-container">{html_dias}</div>',
                        unsafe_allow_html=True,
                    )
                
                # --- 2. Tabela por Ano ---
                st.markdown("<br>", unsafe_allow_html=True) # Espaçamento
                
                tabela_agg['Ano'] = tabela_agg['Data'].dt.year
                soma_anos = tabela_agg.groupby('Ano')['Resultado Total'].sum()
                
                df_anos_final = pd.DataFrame(soma_anos)
                df_anos_final.index.name = "Ano" # Cabeçalho da coluna de índice
                
                styler_anos = df_anos_final.style.format(fmt_res).map(color_res)
                html_anos = styler_anos.to_html(escape=False)
                
                st.markdown(
                    f'<div class="tabela-container">{html_anos}</div>',
                    unsafe_allow_html=True,
                )

        else:
            st.info(
                "Resultado Mensal está oculto. "
                "Clique em 'Mostrar Resultado Mensal' para exibir."
            )

    else:
        st.info(
            "Ajuste os filtros e clique em **Gerar Estatística** "
            "para montar a tabela do Playbook."
        )


# Permite rodar a página isoladamente
if __name__ == "__main__":
    pagina_playbook()