import streamlit as st
import streamlit.components.v1 as components # <-- Importante para o clique funcionar!
import pandas as pd
from pathlib import Path
from datetime import datetime, date, time, timedelta
import math
import numpy as np

# =========================================================
# FUNÇÕES DE FORMATAÇÃO (Reutilizáveis)
# =========================================================

def fmt_res(v):
    """Formata um número para o padrão R$ 1.234,00"""
    if pd.isna(v):
        return ""
    try:
        val = float(v)
        return f"R$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (ValueError, TypeError):
        return str(v)

def color_res(v_str):
    """Cor baseada no valor (lê o formato R$ 1.234,00)"""
    if not isinstance(v_str, str) or not v_str.startswith("R$"):
        try:
            val = float(v_str)
        except (ValueError, TypeError):
            return ""
    else:
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
    return f"{v:,.0f}".replace(",", ".")

def fmt_box(v):
    if pd.isna(v):
        return "" 
    return f"{int(v)}"

# =========================================================
# Carregamento de dados
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
        raise FileNotFoundError("Não encontrei o arquivo 'Playbook-20.xlsx'.")

    df_geral = pd.read_excel(excel_path, sheet_name="Geral")
    df_indicadores = pd.read_excel(excel_path, sheet_name="Indicadores")
    df_geral["Data"] = pd.to_datetime(df_geral["Data"]).dt.date
    df_geral["Hora"] = pd.to_datetime(df_geral["Hora"].astype(str)).dt.time
    df_indicadores["Dia"] = pd.to_datetime(df_indicadores["Dia"]).dt.date
    return df_geral, df_indicadores

# =========================================================
# Lógica operacional (build_playbook_table)
# =========================================================
def build_playbook_table(
    df_geral, df_ind, data_inicio=None, data_fim=None, hora_fim=time(17, 45),
    alvos_config=None, pts_stop=350, usar_trailing=False,
    trailing_trigger=300, trailing_dist=300, dias_semana_selecionados=None
):
    if alvos_config is None or len(alvos_config) == 0:
        alvos_config = [{"alvo": 1, "alvo_pts": 0, "qtd": 1}]
    
    if dias_semana_selecionados is None:
        dias_semana_selecionados = [0, 1, 2, 3, 4, 5, 6]

    df = df_geral.copy()
    ind = df_ind.copy()
    df["Data"] = pd.to_datetime(df["Data"]).dt.date
    df["Hora"] = pd.to_datetime(df["Hora"].astype(str)).dt.time
    ind["Dia"] = pd.to_datetime(ind["Dia"]).dt.date
    ind = ind.rename(columns={"Dia": "Data", "Mínima Injusta": "MinInj", "Máxima Injusta": "MaxInj"})
    df = df.merge(ind, on="Data", how="left")
    df = df.sort_values(["Data", "Box"]).reset_index(drop=True)

    if data_inicio is not None:
        df = df[df["Data"] >= data_inicio]
    if data_fim is not None:
        df = df[df["Data"] <= data_fim]
        
    df["_dia_semana"] = pd.to_datetime(df["Data"]).dt.dayofweek
    df = df[df["_dia_semana"].isin(dias_semana_selecionados)].copy()
    df = df.drop(columns=["_dia_semana"])
    df = df[df["Hora"] <= hora_fim].copy()

    if df.empty:
        return pd.DataFrame()

    df["AbertDia"] = df.groupby("Data")["Abert"].transform("first")
    df["Lado"] = np.where(df["Fec"] > df["Abert"], "Alta", np.where(df["Fec"] < df["Abert"], "Baixa", "Neutro"))

    linhas_saida = []

    for data_dia, df_day in df.groupby("Data"):
        df_day = df_day.sort_values("Box").reset_index(drop=True)
        row_box1 = df_day[df_day["Box"] == 1]
        if row_box1.empty: row_box1 = df_day.iloc[[0]]
        row_box1 = row_box1.iloc[0]

        vah = float(row_box1["VAH"]) if not pd.isna(row_box1["VAH"]) else math.nan
        val = float(row_box1["VAL"]) if not pd.isna(row_box1["VAL"]) else math.nan
        min_inj = float(row_box1["MinInj"]) if not pd.isna(row_box1["MinInj"]) else math.nan
        max_inj = float(row_box1["MaxInj"]) if not pd.isna(row_box1["MaxInj"]) else math.nan
        abrir = float(row_box1["Abert"])
        abert_dia = float(row_box1["AbertDia"])

        if not math.isnan(min_inj) and abrir <= min_inj: cenario = 4
        elif not math.isnan(max_inj) and abrir >= max_inj: cenario = 5
        elif not math.isnan(val) and not math.isnan(vah) and val <= abrir <= vah: cenario = 1
        elif not math.isnan(val) and not math.isnan(min_inj) and min_inj < abrir < val: cenario = 2
        elif not math.isnan(vah) and not math.isnan(max_inj) and vah < abrir < max_inj: cenario = 3
        else: cenario = 0

        entrada = ""
        entrada_box = None
        entrada_row = None
        entrada_price = None
        
        if cenario == 1:
            df_after = df_day[df_day["Box"] > row_box1["Box"]]
            idx_val = df_after[df_after["Mínima"] <= val].index.min() if not math.isnan(val) else None
            box_val = int(df_after.loc[idx_val, "Box"]) if pd.notna(idx_val) else None
            
            idx_vah = df_after[df_after["Máxima"] >= vah].index.min() if not math.isnan(vah) else None
            box_vah = int(df_after.loc[idx_vah, "Box"]) if pd.notna(idx_vah) else None

            if box_val is None and box_vah is None:
                entrada = "Não encontrado"; entrada_box = int(row_box1["Box"]); entrada_row = row_box1
            else:
                if box_val is not None and (box_vah is None or box_val < box_vah):
                    entrada = "Compra"; entrada_box = box_val; entrada_row = df_after[df_after["Box"] == box_val].iloc[0]
                elif box_vah is not None and (box_val is None or box_vah < box_val):
                    entrada = "Venda"; entrada_box = box_vah; entrada_row = df_after[df_after["Box"] == box_vah].iloc[0]
                else:
                    entrada = "Não encontrado"; entrada_box = int(row_box1["Box"]); entrada_row = row_box1
        elif cenario in (2, 5):
            entrada = "Compra"; entrada_box = int(row_box1["Box"]); entrada_row = row_box1
        elif cenario in (3, 4):
            entrada = "Venda"; entrada_box = int(row_box1["Box"]); entrada_row = row_box1
        else:
            entrada = ""; entrada_box = int(row_box1["Box"]); entrada_row = row_box1

        if entrada_row is not None:
            entrada_price = float(entrada_row["Abert"]) if entrada_box == 1 else float(entrada_row["Fec"])

        df_after_entry = df_day[df_day["Box"] > entrada_box] if entrada_box is not None else df_day.iloc[0:0]
        stop_box = None; stop_price_static = None; valor_ponto = 0.2

        if entrada in ("Compra", "Venda") and entrada_price is not None:
            if entrada == "Compra":
                stop_price_static = (entrada_row["Abert"] if entrada_box == 1 else entrada_row["Fec"]) - pts_stop
            else:
                stop_price_static = (entrada_row["Abert"] if entrada_box == 1 else entrada_row["Fec"]) + pts_stop

            if not usar_trailing:
                cond_stop = df_after_entry["Fec"] <= stop_price_static if entrada == "Compra" else df_after_entry["Fec"] >= stop_price_static
                idx_stop = df_after_entry[cond_stop].index.min()
                if isinstance(idx_stop, (int, np.integer)): stop_box = int(df_after_entry.loc[idx_stop, "Box"])

        alvo_boxes = {}; resultados = []

        for idx_alvo, cfg in enumerate(alvos_config, start=1):
            pts = cfg.get("alvo_pts", 0); qtd = cfg.get("qtd", 1)
            res = 0.0; alvo_box = None
            
            if entrada not in ("Compra", "Venda") or entrada_price is None or pts <= 0:
                alvo_boxes[idx_alvo] = None; resultados.append(0.0); continue

            if not usar_trailing:
                target_price = (entrada_row["Abert"] if entrada_box == 1 else entrada_row["Fec"]) + pts if entrada == "Compra" else (entrada_row["Abert"] if entrada_box == 1 else entrada_row["Fec"]) - pts
                cond_target = df_after_entry["Fec"] >= target_price if entrada == "Compra" else df_after_entry["Fec"] <= target_price
                idx_target = df_after_entry[cond_target].index.min()
                if isinstance(idx_target, (int, np.integer)): alvo_box = int(df_after_entry.loc[idx_target, "Box"])
                
                if alvo_box is None and stop_box is None:
                    last_row = df_day.iloc[-1]; close_price = float(last_row["Fec"])
                    res = (close_price - entrada_price if entrada == "Compra" else entrada_price - close_price) * valor_ponto * qtd
                elif alvo_box is not None and (stop_box is None or alvo_box < stop_box):
                    res = pts * valor_ponto * qtd
                else:
                    res = -pts_stop * valor_ponto * qtd
            else:
                # Lógica Trailing Stop
                target_price = entrada_price + pts if entrada == "Compra" else entrada_price - pts
                current_stop_val = stop_price_static
                trade_closed = False
                
                for i, row in df_after_entry.iterrows():
                    curr_high = float(row["Máxima"]); curr_low = float(row["Mínima"]); curr_box = int(row["Box"])
                    
                    hit_stop = False; exit_price_sim = 0.0
                    if entrada == "Compra":
                        if curr_low <= current_stop_val: hit_stop = True; exit_price_sim = current_stop_val
                    else:
                        if curr_high >= current_stop_val: hit_stop = True; exit_price_sim = current_stop_val
                    
                    if hit_stop:
                        trade_closed = True; stop_box = curr_box
                        res = (exit_price_sim - entrada_price if entrada == "Compra" else entrada_price - exit_price_sim) * valor_ponto * qtd
                        break

                    hit_target = False
                    if entrada == "Compra":
                        if curr_high >= target_price: hit_target = True; exit_price_sim = target_price
                    else:
                        if curr_low <= target_price: hit_target = True; exit_price_sim = target_price
                    
                    if hit_target:
                        trade_closed = True; alvo_box = curr_box
                        res = pts * valor_ponto * qtd
                        break
                    
                    if entrada == "Compra":
                        if (curr_high - entrada_price) >= trailing_trigger:
                            new_stop = curr_high - trailing_dist
                            if new_stop > current_stop_val: current_stop_val = new_stop
                    else:
                        if (entrada_price - curr_low) >= trailing_trigger:
                            new_stop = curr_low + trailing_dist
                            if new_stop < current_stop_val: current_stop_val = new_stop

                if not trade_closed:
                    last_row = df_day.iloc[-1]; close_price = float(last_row["Fec"])
                    res = (close_price - entrada_price if entrada == "Compra" else entrada_price - close_price) * valor_ponto * qtd

            alvo_boxes[idx_alvo] = alvo_box; resultados.append(res)

        resultado_total = float(sum(resultados))
        linha = {
            "Data": entrada_row["Data"], "Hora": entrada_row["Hora"], "Abert": entrada_row["Abert"],
            "Máxima": entrada_row["Máxima"], "Mínima": entrada_row["Mínima"], "Fech": entrada_row["Fec"],
            "Box": entrada_row["Box"], "Abert. Dia": abert_dia, "VAH": vah, "VAL": val,
            "Max Inj": max_inj, "Min Inj": min_inj, "Lado": entrada_row["Lado"],
            "Cenário": cenario, "Entrada": entrada, "Stop": stop_box, "Resultado Total": resultado_total
        }
        for i in range(1, len(alvos_config) + 1):
            linha[f"Alvo-{i}"] = alvo_boxes.get(i)
            linha[f"Add-{i}"] = cfg.get("qtd", 1) if entrada in ("Compra", "Venda") else 0
            linha[f"Res-{i}"] = resultados[i-1]
        linhas_saida.append(linha)

    if not linhas_saida: return pd.DataFrame()
    resultado_df = pd.DataFrame(linhas_saida)
    
    # Colunas e Ordem
    cols_base = ["Data", "Hora", "Abert", "Máxima", "Mínima", "Fech", "Box", "Abert. Dia", "VAH", "VAL", "Max Inj", "Min Inj", "Lado", "Cenário", "Entrada"]
    cols_alvo = [f"Alvo-{i}" for i in range(1, len(alvos_config) + 1)]
    cols_add = [f"Add-{i}" for i in range(1, len(alvos_config) + 1)]
    cols_res = [f"Res-{i}" for i in range(1, len(alvos_config) + 1)]
    cols = cols_base + cols_alvo + ["Stop"] + cols_add + cols_res + ["Resultado Total"]
    
    cols_existentes = [c for c in cols if c in resultado_df.columns]
    resultado_df = resultado_df[cols_existentes]

    # Cálculo Dia-Dia
    if "Resultado Total" in resultado_df.columns:
        resultado_df["Data"] = pd.to_datetime(resultado_df["Data"])
        resultado_df = resultado_df.sort_values(by=["Data", "Hora"], ascending=True)
        resultado_df["MesAno"] = resultado_df["Data"].dt.to_period("M")
        resultado_df["Dia-Dia"] = resultado_df.groupby("MesAno")["Resultado Total"].cumsum()
        resultado_df = resultado_df.drop(columns=["MesAno"])
        
        cols_finais = list(resultado_df.columns)
        # Reordena para Dia-Dia ficar após Resultado Total
        if "Resultado Total" in cols_finais and "Dia-Dia" in cols_finais:
            cols_finais.remove("Dia-Dia")
            idx = cols_finais.index("Resultado Total")
            cols_finais.insert(idx + 1, "Dia-Dia")
        resultado_df = resultado_df[cols_finais]

    resultado_df = resultado_df.sort_values(["Data", "Hora"], ascending=[False, False]).reset_index(drop=True)
    return resultado_df

def format_playbook_table_for_display(tabela: pd.DataFrame):
    df = tabela.copy()
    df = df.reset_index(drop=True)
    
    price_cols = ["Abert", "Máxima", "Mínima", "Fech", "Abert. Dia", "VAH", "VAL", "Max Inj", "Min Inj"]
    box_cols = [c for c in df.columns if c.startswith("Alvo-")] + (["Stop"] if "Stop" in df.columns else [])
    res_cols = [c for c in df.columns if c.startswith("Res-")] + (["Resultado Total", "Dia-Dia"] if "Resultado Total" in df.columns else [])
    
    for col in price_cols: 
        if col in df.columns: df[col] = pd.to_numeric(df[col], errors="coerce")
    for col in box_cols: 
        if col in df.columns: df[col] = pd.to_numeric(df[col], errors="coerce")
    for col in res_cols: 
        if col in df.columns: df[col] = pd.to_numeric(df[col], errors="coerce")

    styler = df.style
    fmt_dict = {}
    if "Data" in df.columns: fmt_dict["Data"] = fmt_data
    for col in price_cols: 
        if col in df.columns: fmt_dict[col] = fmt_price
    for col in box_cols: 
        if col in df.columns: fmt_dict[col] = fmt_box
    for col in res_cols: 
        if col in df.columns: fmt_dict[col] = fmt_res

    styler = styler.format(fmt_dict, na_rep="")

    def color_lado(v): return "color: #22c55e;" if v == "Alta" else "color: #ef4444;" if v == "Baixa" else "color: #e5e7eb;"
    def color_entrada(v): return "color: #3b82f6;" if v == "Compra" else "color: #d946ef;" if v == "Venda" else "color: #e5e7eb;"

    if "Lado" in df.columns: styler = styler.map(color_lado, subset=["Lado"])
    if "Entrada" in df.columns: styler = styler.map(color_entrada, subset=["Entrada"])
    
    exist_res = [c for c in res_cols if c in df.columns]
    if exist_res: styler = styler.map(color_res, subset=exist_res)
    
    styler = styler.hide(axis="index")
    return styler.to_html(escape=False)

# =========================================================
# Página Playbook
# =========================================================
def pagina_playbook():
    st.set_page_config(layout="wide")
    st.title("Playbook - Gabriel Pinotti")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("""<div style="background-color: #0b1120; border-radius: 0.75rem; border: 1px solid #3b82f6; padding: 1rem 1.25rem; margin-top: 0.75rem;">
              <h4 style="margin: 0 0 0.5rem 0; color: #bfdbfe;">Cenário 1</h4>
              <p style="margin: 0; line-height: 1.5; font-size: 0.9rem;">Abertura entre <b>VAL</b> ou <b>VAH</b>.<br>Compra na <b>VAL</b> e Venda na <b>VAH</b><br></p></div>""", unsafe_allow_html=True)
    with col2:
        st.markdown("""<div style="background-color: #0b1120; border-radius: 0.75rem; border: 1px solid #22c55e; padding: 1rem 1.25rem; margin-top: 0.75rem;">
              <h4 style="margin: 0 0 0.5rem 0; color: #bbf7d0;">Cenário 2</h4>
              <p style="margin: 0; line-height: 1.5; font-size: 0.9rem;">Abertura entre <b>VAL</b> e <b>Min Injusta</b>.<br>Entrada: <b>Compra a Mercado</b>.</p></div>""", unsafe_allow_html=True)
    with col3:
        st.markdown("""<div style="background-color: #0b1120; border-radius: 0.75rem; border: 1px solid #f97316; padding: 1rem 1.25rem; margin-top: 0.75rem;">
              <h4 style="margin: 0 0 0.5rem 0; color: #fed7aa;">Cenário 3</h4>
              <p style="margin: 0; line-height: 1.5; font-size: 0.9rem;">Abertura entre <b>VAH</b> e <b>Max Injusta</b>.<br>Entrada: <b>Venda a Mercado</b>.</p></div>""", unsafe_allow_html=True)

    col4, col5, col6 = st.columns(3)
    with col4:
        st.markdown("""<div style="background-color: #0b1120; border-radius: 0.75rem; border: 1px solid #eab308; padding: 1rem 1.25rem; margin-top: 0.75rem;">
              <h4 style="margin: 0 0 0.5rem 0; color: #facc15;">Cenário 4</h4>
              <p style="margin: 0; line-height: 1.5; font-size: 0.9rem;">Abertura <b>abaixo</b> da <b>Min Injusta</b>.<br>Entrada: <b>Venda a Mercado</b>.</p></div>""", unsafe_allow_html=True)
    with col5:
        st.markdown("""<div style="background-color: #0b1120; border-radius: 0.75rem; border: 1px solid #a855f7; padding: 1rem 1.25rem; margin-top: 0.75rem;">
              <h4 style="margin: 0 0 0.5rem 0; color: #e9d5ff;">Cenário 5</h4>
              <p style="margin: 0; line-height: 1.5; font-size: 0.9rem;">Abertura <b>acima</b> da <b>Max Injusta</b>.<br>Entrada: <b>Compra a Mercado</b>.</p></div>""", unsafe_allow_html=True)

    # CSS Global (para as outras tabelas e estrutura)
    st.markdown("""
        <style>
        .tabela-container { width: 100%; border-collapse: collapse; }
        .tabela-container th { text-align: center !important; padding: 8px 12px; background-color: #1a202c; color: #cbd5e1; border: 1px solid #2d3748; position: sticky; top: 0; z-index: 1; }
        .tabela-container td { text-align: center !important; padding: 8px 12px; border: 1px solid #2d3748; color: #e5e7eb; white-space: nowrap; }
        .tabela-container tbody tr:nth-child(even) { background-color: #1f2937; }
        .tabela-container tbody tr:nth-child(odd) { background-color: #111827; }
        </style>
        """, unsafe_allow_html=True)

    try:
        df_geral, df_indicadores = load_playbook_data()
    except FileNotFoundError as e:
        st.error(str(e)); return

    min_data = df_geral["Data"].min(); max_data = df_geral["Data"].max()

    st.sidebar.header("Filtros")
    data_inicio = st.sidebar.date_input("Data de Início", value=min_data, min_value=min_data, max_value=max_data, format="DD/MM/YYYY")
    data_fim = st.sidebar.date_input("Data de Fim", value=max_data, min_value=min_data, max_value=max_data, format="DD/MM/YYYY")

    hora_opcoes = []
    curr = datetime.combine(date.today(), time(12, 0)); end = datetime.combine(date.today(), time(18, 0))
    while curr <= end: hora_opcoes.append(curr.strftime("%H:%M")); curr += timedelta(minutes=15)
    hora_fim_str = st.sidebar.selectbox("Hora Fim", options=hora_opcoes, index=hora_opcoes.index("17:45"))

    qtde_alvos = st.sidebar.number_input("Qtde. Alvos", min_value=1, max_value=10, value=1, step=1)
    st.sidebar.markdown("---")
    alvos_config = []
    for i in range(1, qtde_alvos + 1):
        st.sidebar.markdown(f"**Alvo {i}**")
        alvo_pts = st.sidebar.number_input(f"Alvo {i} (pts)", min_value=0, step=50, value=700, key=f"alvo_{i}_pts")
        qtd_contratos = st.sidebar.number_input(f"Qtde {i}", min_value=1, step=1, value=1, key=f"alvo_{i}_qtd")
        alvos_config.append({"alvo": i, "alvo_pts": alvo_pts, "qtd": qtd_contratos})

    st.sidebar.markdown("---")
    pts_stop = st.sidebar.number_input("Pts. Stop", min_value=50, max_value=5000, step=50, value=350)
    
    st.sidebar.markdown("---")
    usar_trailing = st.sidebar.checkbox("Ativar Trailing Stop", value=False)
    trailing_trigger = 300; trailing_dist = 300
    if usar_trailing:
        c1, c2 = st.sidebar.columns(2)
        trailing_trigger = c1.number_input("Gatilho (pts)", 0, step=50, value=300)
        trailing_dist = c2.number_input("Distância (pts)", 0, step=50, value=300)

    st.sidebar.markdown("---")
    st.sidebar.markdown("**Dias da Semana**")
    dias_map = {0: "Seg", 1: "Ter", 2: "Qua", 3: "Qui", 4: "Sex"}
    dias_selecionados = []
    cd = st.sidebar.columns(3)
    idx = 0
    for dn, nome in dias_map.items():
        with cd[idx % 3]:
            if st.checkbox(nome, value=True, key=f"dia_{dn}"): dias_selecionados.append(dn)
        idx += 1

    st.sidebar.markdown("---")
    if st.sidebar.button("Gerar Estatística"): st.session_state["playbook_gerado"] = True
    if "playbook_gerado" not in st.session_state: st.session_state["playbook_gerado"] = False

    st.markdown("---")
    if "mostrar_tabela_playbook" not in st.session_state: st.session_state["mostrar_tabela_playbook"] = True
    txt_btn = "Ocultar Tabela" if st.session_state["mostrar_tabela_playbook"] else "Mostrar Tabela"
    if st.button(txt_btn):
        st.session_state["mostrar_tabela_playbook"] = not st.session_state["mostrar_tabela_playbook"]
        st.rerun()

    if st.session_state["playbook_gerado"]:
        hora_fim = datetime.strptime(hora_fim_str, "%H:%M").time()
        tabela = build_playbook_table(
            df_geral, df_indicadores, data_inicio, data_fim, hora_fim,
            alvos_config, pts_stop, usar_trailing, trailing_trigger, trailing_dist, dias_selecionados
        )

        if tabela.empty:
            st.warning("Nenhum dado encontrado.")
            return

        if st.session_state["mostrar_tabela_playbook"]:
            st.subheader("Tabela Playbook - Operações por Dia")
            html_table = format_playbook_table_for_display(tabela)
            
            # =========================================================================
            # IFRAME COMPLETO PARA PERMITIR CLIQUE + CSS
            # =========================================================================
            html_completo = f"""
            <html>
            <head>
            <style>
                body {{ font-family: sans-serif; margin: 0; padding: 0; background-color: #0e1117; color: #fafafa; }}
                .tabela-container {{ width: 100%; border-collapse: collapse; }}
                th {{ position: sticky; top: 0; z-index: 10; background-color: #1a202c; color: #cbd5e1; padding: 8px 12px; border: 1px solid #2d3748; text-align: center; }}
                td {{ padding: 8px 12px; border: 1px solid #2d3748; color: #e5e7eb; text-align: center; white-space: nowrap; }}
                tr:nth-child(even) {{ background-color: #1f2937; }}
                tr:nth-child(odd) {{ background-color: #111827; }}
                
                /* EFEITO HOVER e CLICK */
                tbody tr:hover {{ background-color: #374151 !important; cursor: pointer; }}
                tbody tr.selected {{ background-color: #4b5563 !important; border-left: 4px solid #60a5fa; }}
                tbody tr.selected td {{ color: #ffffff !important; font-weight: bold; }}
            </style>
            </head>
            <body>
                {html_table}
                <script>
                    // Adiciona evento de clique em cada linha
                    const rows = document.querySelectorAll('tbody tr');
                    rows.forEach(row => {{
                        row.addEventListener('click', function() {{
                            this.classList.toggle('selected');
                        }});
                    }});
                </script>
            </body>
            </html>
            """
            
            # Renderiza usando components.html (Isolado = Scripts funcionam!)
            components.html(html_completo, height=700, scrolling=True)
            
        else:
            st.info("Tabela Playbook está oculta.")

        st.markdown("---")
        if "mostrar_tabela_mensal" not in st.session_state: st.session_state["mostrar_tabela_mensal"] = True
        txt_mes = "Ocultar Resultado Mensal" if st.session_state["mostrar_tabela_mensal"] else "Mostrar Resultado Mensal"
        if st.button(txt_mes):
            st.session_state["mostrar_tabela_mensal"] = not st.session_state["mostrar_tabela_mensal"]
            st.rerun()

        if st.session_state["mostrar_tabela_mensal"]:
            col_mensal, col_stats = st.columns([3, 2])
            
            # Prepara DF Mensal
            tab_agg = tabela.copy()
            tab_agg['Data'] = pd.to_datetime(tab_agg['Data'])
            tab_agg['MesAno'] = tab_agg['Data'].dt.to_period('M')
            
            res_men = tab_agg.groupby('MesAno').agg(
                **{'Resultado Total': ('Resultado Total', 'sum'), 'Exp Max Neg': ('Dia-Dia', 'min')}
            ).reset_index().sort_values('MesAno', ascending=False)
            
            mes_map = {1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril', 5: 'Maio', 6: 'Junho', 7: 'Julho', 8: 'Agosto', 9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'}
            res_men['Mês'] = res_men['MesAno'].dt.month.map(mes_map) + " " + res_men['MesAno'].dt.year.astype(str)
            res_men = res_men[['Mês', 'Resultado Total', 'Exp Max Neg']]
            
            styler_m = res_men.style.format({'Resultado Total': fmt_res, 'Exp Max Neg': fmt_res}).map(color_res, subset=['Resultado Total', 'Exp Max Neg']).hide(axis="index")
            
            with col_mensal:
                st.subheader("Resultado Mensal")
                st.markdown(f'<div class="tabela-container">{styler_m.to_html(escape=False)}</div>', unsafe_allow_html=True)

            with col_stats:
                st.subheader("Resumo por Período")
                tab_agg['DiaSemana'] = tab_agg['Data'].dt.dayofweek
                dmap = {0: 'Seg', 1: 'Ter', 2: 'Qua', 3: 'Qui', 4: 'Sex'}
                df_d = tab_agg[tab_agg['DiaSemana'].isin(dmap.keys())].copy()
                if not df_d.empty:
                    sd = df_d.groupby('DiaSemana')['Resultado Total'].sum().reindex(dmap.keys(), fill_value=0)
                    sd.index = sd.index.map(dmap); df_d_final = pd.DataFrame(sd).T; df_d_final.index = ["Resultado"]
                    sty_d = df_d_final.style.format(fmt_res).map(color_res).hide(axis="index")
                    st.markdown(f'<div class="tabela-container">{sty_d.to_html(escape=False)}</div>', unsafe_allow_html=True)
                
                st.markdown("<br>", unsafe_allow_html=True)
                tab_agg['Ano'] = tab_agg['Data'].dt.year
                sa = tab_agg.groupby('Ano')['Resultado Total'].sum()
                df_a = pd.DataFrame(sa); df_a.index.name = "Ano"
                sty_a = df_a.style.format(fmt_res).map(color_res)
                st.markdown(f'<div class="tabela-container">{sty_a.to_html(escape=False)}</div>', unsafe_allow_html=True)
        else:
            st.info("Resultado Mensal está oculto.")
    else:
        st.info("Ajuste os filtros e clique em **Gerar Estatística**.")

if __name__ == "__main__":
    pagina_playbook()