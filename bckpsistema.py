import streamlit as st
import pandas as pd
import plotly.express as px
from fpdf import FPDF
import os
import time
from datetime import datetime, timedelta
from io import BytesIO
import xml.etree.ElementTree as ET
from xml.dom import minidom
import zipfile
import json

# --- Configuração da Página ---
st.set_page_config(
    page_title="Gestão de Pizzaria - GMaster",
    page_icon="🍕",
    layout="wide"
)

# --- Estilo CSS Personalizado ---
# Ajustado para tema escuro com letras brancas para melhor visualização.
st.markdown("""
<style>
    .stApp {
        background-color: #262730; /* Fundo escuro para a aplicação */
    }
    .stApp, .stApp *, .st-emotion-cache-10trblm, .st-emotion-cache-1y4p8pa, .st-emotion-cache-1v0mbdj, .e115fcil1 {
        color: #FFFFFF !important; /* Força o texto a ser branco */
    }
    h2 {
        color: #b71c1c !important; /* Cor dos títulos principais (vermelho escuro) */
        font-weight: bold;
    }
    .stButton>button {
        background-color: #ffc107; /* Cor do botão (amarelo) */
        color: black !important; /* Texto do botão preto */
        border-radius: 8px;
        border: none;
        padding: 10px 20px;
        font-weight: bold;
    }
    .stButton>button:hover {
        background-color: #ffa000; /* Cor do botão ao passar o mouse */
    }
    /* Cor do texto dentro dos inputs e selects */
    .stTextInput input, .stSelectbox select, .stNumberInput input, .stDateInput input {
        color: #000000 !important;
    }
</style>
""", unsafe_allow_html=True)

# --- Caminhos dos Ficheiros ---
try:
    BASE_DIR = os.path.dirname(os.path.realpath(__file__))
except NameError:
    BASE_DIR = os.getcwd()
DB_FILE = os.path.join(BASE_DIR, "pizzaria_db.xlsx")
CONFIG_FILE = os.path.join(BASE_DIR, "config_empresa.json")


# --- Funções de Manipulação de Dados ---
def criar_db_modelo():
    df_produtos = pd.DataFrame(columns=['Produto', 'Categoria', 'Preco_Venda', 'Custo_Unitario'])
    df_estoque = pd.DataFrame(columns=['Produto', 'Quantidade_Estoque'])
    df_vendas = pd.DataFrame(columns=['Data', 'Produto', 'Quantidade', 'CPF_Cliente'])
    df_compras = pd.DataFrame(columns=['Data', 'Item', 'Valor', 'Fornecedor', 'Categoria_Despesa'])
    
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_produtos.to_excel(writer, index=False, sheet_name='Cardapio')
        df_estoque.to_excel(writer, index=False, sheet_name='Estoque')
        df_vendas.to_excel(writer, index=False, sheet_name='Vendas')
        df_compras.to_excel(writer, index=False, sheet_name='Compras')
    
    return output.getvalue()

def inicializar_arquivos():
    st.info("Base de dados não encontrada. Criando arquivos iniciais...")
    config_default = {
        "nome_fantasia": "Pizzaria Casa Velha", "razao_social": "Pizzaria Casa Velha LTDA",
        "cnpj": "00.000.000/0001-00", "endereco": "Rua das Pizzas, 123, Bairro Centro",
        "cidade_uf": "Sua Cidade - UF", "telefone": "(00) 00000-0000"
    }
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config_default, f, indent=4)
    db_modelo_data = criar_db_modelo()
    with open(DB_FILE, "wb") as f:
        f.write(db_modelo_data)
    st.success("Arquivos de base de dados criados com sucesso!")
    st.info("A aplicação será recarregada em 3 segundos...")
    time.sleep(3)
    st.rerun()

def carregar_dados_para_edicao():
    if not os.path.exists(DB_FILE) or not os.path.exists(CONFIG_FILE):
        inicializar_arquivos()
    try:
        with open(DB_FILE, 'rb') as f:
            xls = pd.ExcelFile(f)
            st.session_state['df_produtos'] = pd.read_excel(xls, 'Cardapio')
            st.session_state['df_estoque'] = pd.read_excel(xls, 'Estoque')
            st.session_state['df_vendas'] = pd.read_excel(xls, 'Vendas')
            if 'Compras' in xls.sheet_names:
                st.session_state['df_compras'] = pd.read_excel(xls, 'Compras')
            else: 
                st.session_state['df_compras'] = pd.DataFrame(columns=['Data', 'Item', 'Valor', 'Fornecedor', 'Categoria_Despesa'])
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            st.session_state['config_empresa'] = json.load(f)
    except Exception as e:
        st.error(f"Ocorreu um erro ao carregar os dados: {e}")
        st.warning(f"Verifique se os ficheiros de dados não estão corrompidos. Se necessário, apague-os para que o sistema os crie novamente.")
        st.stop()
        
def salvar_dados(config_empresa, produtos, estoque, vendas, compras):
    produtos_df = produtos.dropna(subset=['Produto'])
    produtos_atuais = produtos_df['Produto'].unique()
    estoque_sincronizado = estoque[estoque['Produto'].isin(produtos_atuais)].copy()
    novos_produtos = [p for p in produtos_atuais if p not in estoque_sincronizado['Produto'].values]
    if novos_produtos:
        novos_estoque_df = pd.DataFrame({'Produto': novos_produtos, 'Quantidade_Estoque': [0]*len(novos_produtos)})
        estoque_sincronizado = pd.concat([estoque_sincronizado, novos_estoque_df], ignore_index=True)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        produtos_df.to_excel(writer, index=False, sheet_name='Cardapio')
        estoque_sincronizado.to_excel(writer, index=False, sheet_name='Estoque')
        vendas.to_excel(writer, index=False, sheet_name='Vendas')
        compras.to_excel(writer, index=False, sheet_name='Compras')
    with open(DB_FILE, "wb") as f:
        f.write(output.getvalue())
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config_empresa, f, indent=4)
    st.toast("🎉 Dados salvos com sucesso!", icon='✅')

def gerar_xml_nfc(venda_info, produtos_info):
    nfe = ET.Element("NFe", xmlns="http://www.portalfiscal.inf.br/nfe")
    infNFe = ET.SubElement(nfe, "infNFe", versao="4.00")
    ide = ET.SubElement(infNFe, "ide")
    ET.SubElement(ide, "cUF").text = "50" 
    ET.SubElement(ide, "natOp").text = "VENDA"
    ET.SubElement(ide, "mod").text = "65" 
    ET.SubElement(ide, "serie").text = "1"
    ET.SubElement(ide, "nNF").text = str(venda_info.name + 1) 
    ET.SubElement(ide, "dhEmi").text = pd.to_datetime(venda_info['Data']).isoformat()
    emit = ET.SubElement(infNFe, "emit")
    ET.SubElement(emit, "CNPJ").text = st.session_state['config_empresa'].get('cnpj', '').replace('.', '').replace('/', '').replace('-', '')
    ET.SubElement(emit, "xNome").text = st.session_state['config_empresa'].get('razao_social', '')
    if 'CPF_Cliente' in venda_info and pd.notna(venda_info['CPF_Cliente']):
        dest = ET.SubElement(infNFe, "dest")
        ET.SubElement(dest, "CPF").text = str(venda_info['CPF_Cliente']).replace('.', '').replace('-', '')
    total_nota = 0
    for i, row in produtos_info.reset_index(drop=True).iterrows():
        det = ET.SubElement(infNFe, "det", nItem=str(i + 1))
        prod = ET.SubElement(det, "prod")
        ET.SubElement(prod, "cProd").text = f"P{i+1}"
        ET.SubElement(prod, "xProd").text = row['Produto']
        ET.SubElement(prod, "NCM").text = "21069090" 
        ET.SubElement(prod, "CFOP").text = "5102"
        ET.SubElement(prod, "uCom").text = "UN"
        ET.SubElement(prod, "qCom").text = f"{row['Quantidade']:.4f}"
        ET.SubElement(prod, "vUnCom").text = f"{row['Preco_Venda']:.10f}"
        vProd = row['Quantidade'] * row['Preco_Venda']
        total_nota += vProd
        ET.SubElement(prod, "vProd").text = f"{vProd:.2f}"
        ET.SubElement(prod, "uTrib").text = "UN"
        ET.SubElement(prod, "qTrib").text = f"{row['Quantidade']:.4f}"
        ET.SubElement(prod, "vUnTrib").text = f"{row['Preco_Venda']:.10f}"
        ET.SubElement(prod, "indTot").text = "1"
    total = ET.SubElement(infNFe, "total")
    ICMSTot = ET.SubElement(total, "ICMSTot")
    ET.SubElement(ICMSTot, "vBC").text = "0.00"
    ET.SubElement(ICMSTot, "vICMS").text = "0.00"
    ET.SubElement(ICMSTot, "vProd").text = f"{total_nota:.2f}"
    ET.SubElement(ICMSTot, "vNF").text = f"{total_nota:.2f}"
    pag = ET.SubElement(infNFe, "pag")
    detPag = ET.SubElement(pag, "detPag")
    ET.SubElement(detPag, "tPag").text = "01" 
    ET.SubElement(detPag, "vPag").text = f"{total_nota:.2f}"
    xml_string = ET.tostring(nfe, 'utf-8')
    dom = minidom.parseString(xml_string)
    return dom.toprettyxml(indent="  ", encoding="utf-8")

def gerar_script_mysql(produtos, estoque, vendas):
    sql_script = ""
    sql_script += "DROP TABLE IF EXISTS `cardapio`;\n"
    sql_script += "CREATE TABLE `cardapio` (`Produto` varchar(255) NOT NULL, `Categoria` varchar(255) DEFAULT NULL, `Preco_Venda` decimal(10,2) DEFAULT NULL, `Custo_Unitario` decimal(10,2) DEFAULT NULL, PRIMARY KEY (`Produto`)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;\n\n"
    if not produtos.empty:
        for index, row in produtos.iterrows():
            produto = str(row.get('Produto', '')).replace("'", "''")
            categoria = str(row.get('Categoria', '')).replace("'", "''")
            preco = row.get('Preco_Venda', 0)
            custo = row.get('Custo_Unitario', 0)
            linha_sql = f"INSERT INTO `cardapio` VALUES ('{produto}', '{categoria}', {preco}, {custo});\n"
            sql_script += linha_sql
    sql_script += "\nDROP TABLE IF EXISTS `estoque`;\n"
    sql_script += "CREATE TABLE `estoque` (`Produto` varchar(255) NOT NULL, `Quantidade_Estoque` int(11) DEFAULT NULL, PRIMARY KEY (`Produto`)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;\n\n"
    if not estoque.empty:
        for index, row in estoque.iterrows():
            produto = str(row.get('Produto', '')).replace("'", "''")
            qtde = row.get('Quantidade_Estoque', 0)
            linha_sql = f"INSERT INTO `estoque` VALUES ('{produto}', {qtde});\n"
            sql_script += linha_sql
    sql_script += "\nDROP TABLE IF EXISTS `vendas`;\n"
    sql_script += "CREATE TABLE `vendas` (`id` int(11) NOT NULL AUTO_INCREMENT, `Data` datetime DEFAULT NULL, `Produto` varchar(255) DEFAULT NULL, `Quantidade` int(11) DEFAULT NULL, `CPF_Cliente` varchar(20) DEFAULT NULL, PRIMARY KEY (`id`)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;\n\n"
    if not vendas.empty:
        for index, row in vendas.iterrows():
            data = pd.to_datetime(row.get('Data')).strftime('%Y-%m-%d %H:%M:%S')
            produto = str(row.get('Produto', '')).replace("'", "''")
            qtde = row.get('Quantidade', 0)
            cpf = str(row.get('CPF_Cliente', '')).replace("'", "''")
            linha_sql = f"INSERT INTO `vendas` (`Data`, `Produto`, `Quantidade`, `CPF_Cliente`) VALUES ('{data}', '{produto}', {qtde}, '{cpf}');\n"
            sql_script += linha_sql
    return sql_script.encode('utf-8')

if 'dados_carregados' not in st.session_state:
    carregar_dados_para_edicao()
    st.session_state['dados_carregados'] = True

st.title(f"🍕 {st.session_state['config_empresa'].get('nome_fantasia', 'GMaster')} - GMaster")
tab_list = ["📊 Dashboard", "👑 Central de Desempenho", "💰 Registrar Venda", "📖 Cardápio", "📦 Estoque", "🛒 Compras", "🧾 Emissão Fiscal", "⚙️ Empresa"]
tab_dashboard, tab_admin, tab_vendas, tab_cardapio, tab_estoque, tab_compras, tab_fiscal, tab_empresa = st.tabs(tab_list)

def preparar_dados_analise(vendas_df, produtos_df):
    if vendas_df.empty or produtos_df.empty:
        return pd.DataFrame()
    produtos_df_copy = produtos_df.copy()
    vendas_df_copy = vendas_df.copy()
    produtos_df_copy['Preco_Venda'] = pd.to_numeric(produtos_df_copy['Preco_Venda'], errors='coerce').fillna(0)
    produtos_df_copy['Custo_Unitario'] = pd.to_numeric(produtos_df_copy['Custo_Unitario'], errors='coerce').fillna(0)
    vendas_df_copy['Quantidade'] = pd.to_numeric(vendas_df_copy['Quantidade'], errors='coerce').fillna(0)
    vendas_detalhadas = pd.merge(vendas_df_copy, produtos_df_copy, on='Produto', how='left')
    vendas_validas = vendas_detalhadas[
        (vendas_detalhadas['Preco_Venda'] > 0) & 
        (vendas_detalhadas['Custo_Unitario'] > 0)
    ].copy()
    if not vendas_validas.empty:
        vendas_validas['Receita'] = vendas_validas['Quantidade'] * vendas_validas['Preco_Venda']
        vendas_validas['Lucro'] = vendas_validas['Receita'] - (vendas_validas['Quantidade'] * vendas_validas['Custo_Unitario'])
        vendas_validas['Data'] = pd.to_datetime(vendas_validas['Data'])
        return vendas_validas
    return pd.DataFrame()

# --- Abas de Análise (ATUALIZADAS COM AVISOS) ---
with tab_dashboard:
    st.header("Análise de Desempenho Rápida")
    vendas_detalhadas_dash = preparar_dados_analise(st.session_state['df_vendas'], st.session_state['df_produtos'])
    
    # NOVO: Lógica de avisos
    if vendas_detalhadas_dash.empty:
        st.date_input("Data de Início", datetime.now().date(), key="dash_inicio_empty", disabled=True)
        st.date_input("Data de Fim", datetime.now().date(), key="dash_fim_empty", disabled=True)
        kpi1, kpi2, kpi3 = st.columns(3)
        kpi1.metric("Receita Total", "R$ 0.00")
        kpi2.metric("Lucro Total", "R$ 0.00")
        kpi3.metric("Total de Itens Vendidos", "0")
        if not st.session_state['df_vendas'].empty:
            st.warning("📊 Você tem vendas registradas, mas elas não estão aparecendo nos gráficos! Verifique se os produtos vendidos têm 'Preço de Venda' e 'Custo Unitário' maiores que zero na aba 'Cardápio'.")
        else:
            st.warning("Ainda não há dados de vendas para análise. Registre uma venda e preencha o preço/custo no cardápio para começar.")
    else:
        data_min_real = vendas_detalhadas_dash['Data'].min().date()
        data_max_real = vendas_detalhadas_dash['Data'].max().date()
        data_inicio = pd.to_datetime(st.date_input("Data de Início", data_min_real, key="dash_inicio"))
        data_fim = pd.to_datetime(st.date_input("Data de Fim", data_max_real, key="dash_fim")) + timedelta(days=1)
        vendas_filtradas = vendas_detalhadas_dash[(vendas_detalhadas_dash['Data'] >= data_inicio) & (vendas_detalhadas_dash['Data'] < data_fim)]
        kpi1, kpi2, kpi3 = st.columns(3)
        kpi1.metric("Receita Total", f"R$ {vendas_filtradas['Receita'].sum():.2f}")
        kpi2.metric("Lucro Total", f"R$ {vendas_filtradas['Lucro'].sum():.2f}")
        kpi3.metric("Total de Itens Vendidos", f"{int(vendas_filtradas['Quantidade'].sum())}")
        if not vendas_filtradas.empty:
            g1, g2 = st.columns(2)
            with g1:
                produtos_mais_vendidos = vendas_filtradas.groupby('Produto')['Quantidade'].sum().nlargest(5).sort_values(ascending=True)
                fig_produtos = px.bar(produtos_mais_vendidos, x='Quantidade', y=produtos_mais_vendidos.index, orientation='h', title="🏆 Top 5 Produtos Mais Vendidos")
                st.plotly_chart(fig_produtos, use_container_width=True)
            with g2:
                vendas_categoria = vendas_filtradas.groupby('Categoria')['Receita'].sum().sort_values(ascending=True)
                fig_categoria = px.pie(vendas_categoria, values='Receita', names=vendas_categoria.index, title="💰 Receita por Categoria", hole=0.4)
                st.plotly_chart(fig_categoria, use_container_width=True)
        else:
            st.info("Não há dados de vendas no período selecionado para exibir análises.")

with tab_admin:
    st.header("👑 Central de Desempenho")
    vendas_para_analise = preparar_dados_analise(st.session_state['df_vendas'], st.session_state['df_produtos'])
    
    # NOVO: Lógica de avisos melhorada
    if vendas_para_analise.empty:
        if not st.session_state['df_vendas'].empty:
            st.warning("📊 Você tem vendas registradas, mas elas não estão aparecendo nos gráficos! Verifique se os produtos vendidos têm 'Preço de Venda' e 'Custo Unitário' maiores que zero na aba 'Cardápio'.")
        else:
            st.warning("Os gráficos estão sendo exibidos com valores zerados porque não há vendas válidas registradas.")
        vendas_para_analise = pd.DataFrame({'Data': [datetime.now()], 'Receita': [0], 'Categoria': ['Nenhuma'], 'Lucro': [0], 'Produto': ['Nenhum']})

    vendas_para_analise['Dia_da_Semana'] = pd.to_datetime(vendas_para_analise['Data']).dt.day_name()
    st.subheader("Desempenho Geral")
    g1, g2 = st.columns(2)
    with g1:
        vendas_dia = vendas_para_analise.groupby(pd.to_datetime(vendas_para_analise['Data']).dt.date)['Receita'].sum()
        fig_dia = px.line(vendas_dia, x=vendas_dia.index, y='Receita', title="📈 Receita Diária", markers=True, labels={'x':'Data', 'Receita':'Receita (R$)'})
        fig_dia.update_layout(yaxis_range=[0, max(1, vendas_dia.max() or 1)])
        st.plotly_chart(fig_dia, use_container_width=True)
    with g2:
        vendas_categoria = vendas_para_analise.groupby('Categoria')['Receita'].sum().sort_values(ascending=False)
        vendas_categoria = vendas_categoria[vendas_categoria.index.notna() & (vendas_categoria.index != '')]
        fig_cat_pie = px.pie(vendas_categoria, values='Receita', names=vendas_categoria.index, title="🍕 Receita por Categoria", hole=0.4)
        st.plotly_chart(fig_cat_pie, use_container_width=True)
    st.divider()
    st.subheader("Análise de Produtos e Dias")
    g3, g4 = st.columns(2)
    with g3:
        dias_ordem = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        vendas_semama = vendas_para_analise.groupby('Dia_da_Semana')['Receita'].sum().reindex(dias_ordem).fillna(0)
        fig_semama = px.bar(vendas_semama, x=vendas_semama.index, y='Receita', title="📅 Vendas por Dia da Semana", labels={'x':'Dia da Semana', 'Receita':'Receita Total (R$)'})
        st.plotly_chart(fig_semama, use_container_width=True)
    with g4:
        top_produtos_lucro = vendas_para_analise.groupby('Produto')['Lucro'].sum().nlargest(10).sort_values()
        top_produtos_lucro = top_produtos_lucro[top_produtos_lucro.index.notna() & (top_produtos_lucro.index != '')]
        fig_top_lucro = px.bar(top_produtos_lucro, x='Lucro', y=top_produtos_lucro.index, orientation='h', title="🏆 Top 10 Produtos por Lucro", labels={'Lucro':'Lucro Total (R$)', 'y':'Produto'})
        st.plotly_chart(fig_top_lucro, use_container_width=True)

# --- Abas de Edição (sem alterações) ---
with tab_vendas:
    st.header("💰 Registrar Nova Venda")
    produtos_disponiveis = st.session_state['df_produtos']['Produto'].tolist() if not st.session_state['df_produtos'].empty else []
    if produtos_disponiveis:
        produto_vendido = st.selectbox("Selecione o Produto", options=produtos_disponiveis, key="venda_produto")
        quantidade_vendida = st.number_input("Quantidade", min_value=1, step=1, key="venda_qtde")
        cpf_cliente = st.text_input("CPF do Cliente (Opcional)", key="venda_cpf")
        if st.button("Confirmar Venda"):
            idx_estoque_list = st.session_state['df_estoque'].index[st.session_state['df_estoque']['Produto'] == produto_vendido].tolist()
            if idx_estoque_list:
                idx_estoque = idx_estoque_list[0]
                estoque_atual = st.session_state['df_estoque'].loc[idx_estoque, 'Quantidade_Estoque']
                if estoque_atual >= quantidade_vendida:
                    st.session_state['df_estoque'].loc[idx_estoque, 'Quantidade_Estoque'] -= quantidade_vendida
                    nova_venda = pd.DataFrame([{'Data': datetime.now(), 'Produto': produto_vendido, 'Quantidade': quantidade_vendida, 'CPF_Cliente': cpf_cliente}])
                    st.session_state['df_vendas'] = pd.concat([st.session_state['df_vendas'], nova_venda], ignore_index=True)
                    salvar_dados(st.session_state['config_empresa'], st.session_state['df_produtos'], st.session_state['df_estoque'], st.session_state['df_vendas'], st.session_state['df_compras'])
                    st.success("Venda registrada e salva com sucesso!")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error(f"Estoque insuficiente! Apenas {int(estoque_atual)} unidade(s) disponível(is).")
            else:
                st.error("Produto sem registro no estoque! Adicione-o na aba Estoque.")
    else:
        st.warning("Adicione produtos no Cardápio para registrar vendas.")

with tab_cardapio:
    st.header("📖 Gerenciar Cardápio")
    st.info("Clique duas vezes numa célula para editar. Adicione ou remova linhas usando os botões `+` e `x`. Salve as alterações no botão abaixo.")
    st.session_state['df_produtos'] = st.data_editor(st.session_state['df_produtos'], num_rows="dynamic", key="editor_produtos")
    if st.button("Salvar Alterações no Cardápio"):
        salvar_dados(st.session_state['config_empresa'], st.session_state['df_produtos'], st.session_state['df_estoque'], st.session_state['df_vendas'], st.session_state['df_compras'])
        time.sleep(1)
        st.rerun()

with tab_estoque:
    st.header("📦 Controlar Estoque")
    produtos_no_cardapio = st.session_state['df_produtos']['Produto'].unique()
    estoque_atual_df = st.session_state['df_estoque']
    estoque_sincronizado = estoque_atual_df[estoque_atual_df['Produto'].isin(produtos_no_cardapio)].copy()
    novos_produtos = [p for p in produtos_no_cardapio if p not in estoque_sincronizado['Produto'].values]
    if novos_produtos:
        novos_estoque_df = pd.DataFrame({'Produto': novos_produtos, 'Quantidade_Estoque': [0]*len(novos_produtos)})
        estoque_sincronizado = pd.concat([estoque_sincronizado, novos_estoque_df], ignore_index=True)
    st.info("A lista de produtos é sincronizada com o Cardápio. Apenas a quantidade pode ser editada aqui. Salve as alterações no botão abaixo.")
    st.session_state['df_estoque'] = st.data_editor(estoque_sincronizado, disabled=['Produto'], key="editor_estoque")
    if st.button("Salvar Alterações no Estoque"):
        salvar_dados(st.session_state['config_empresa'], st.session_state['df_produtos'], st.session_state['df_estoque'], st.session_state['df_vendas'], st.session_state['df_compras'])
        time.sleep(1)
        st.rerun()

with tab_compras:
    st.header("🛒 Registrar Compras e Despesas")
    st.info("Utilize esta secção para registar todas as compras de mercadorias e outras despesas do negócio.")
    with st.form("form_compras", clear_on_submit=True):
        data_compra = st.date_input("Data da Compra", datetime.now())
        item_comprado = st.text_input("Item Comprado / Descrição da Despesa")
        valor_compra = st.number_input("Valor Total Gasto (R$)", min_value=0.0, format="%.2f")
        fornecedor = st.text_input("Fornecedor (Opcional)")
        categoria_despesa = st.selectbox("Categoria da Despesa", ["Mercadorias", "Aluguel", "Salários", "Marketing", "Outros"])
        submitted = st.form_submit_button("Registar Compra")
        if submitted:
            if not item_comprado or valor_compra <= 0:
                st.error("Por favor, preencha a descrição e o valor da compra.")
            else:
                nova_compra = pd.DataFrame([{'Data': data_compra, 'Item': item_comprado, 'Valor': valor_compra, 'Fornecedor': fornecedor, 'Categoria_Despesa': categoria_despesa}])
                st.session_state['df_compras'] = pd.concat([st.session_state['df_compras'], nova_compra], ignore_index=True)
                salvar_dados(st.session_state['config_empresa'], st.session_state['df_produtos'], st.session_state['df_estoque'], st.session_state['df_vendas'], st.session_state['df_compras'])
                st.rerun()
    st.divider()
    st.subheader("Histórico de Compras Recentes")
    st.dataframe(st.session_state['df_compras'].tail(10))

with tab_fiscal:
    st.header("🧾 Emissão Fiscal")
    st.info("Selecione uma venda para gerar o arquivo XML individual.")
    vendas_df_fiscal = st.session_state['df_vendas'].copy()
    if not vendas_df_fiscal.empty:
        vendas_df_fiscal['Data'] = pd.to_datetime(vendas_df_fiscal['Data'])
        vendas_recentes = vendas_df_fiscal.tail(10).sort_index(ascending=False)
        vendas_recentes['display'] = vendas_recentes.apply(lambda row: f"ID {row.name} - {row['Produto']} ({int(row['Quantidade']) if pd.notna(row['Quantidade']) else 0}x) - {row['Data'].strftime('%d/%m/%Y %H:%M')}", axis=1)
        venda_selecionada_display = st.selectbox("Selecione uma Venda Recente", options=vendas_recentes['display'])
        if venda_selecionada_display:
            venda_id = int(venda_selecionada_display.split(" ")[1])
            venda_info = vendas_df_fiscal.loc[venda_id]
            produto_info_venda = st.session_state['df_produtos'][st.session_state['df_produtos']['Produto'] == venda_info['Produto']].copy()
            if not produto_info_venda.empty:
                produto_info_venda['Quantidade'] = venda_info['Quantidade']
                st.write("Detalhes da Venda Selecionada:")
                st.dataframe(pd.DataFrame([venda_info]))
                if st.button("Gerar XML da NFC-e"):
                    xml_data = gerar_xml_nfc(venda_info, produto_info_venda)
                    st.download_button(label="Baixar XML para Emissão", data=xml_data, file_name=f"nfce_{venda_id}.xml", mime="application/xml")
            else:
                st.error("Produto associado a esta venda não foi encontrado no cardápio atual.")
    else:
        st.warning("Nenhuma venda registrada para gerar XML.")
    st.divider()
    st.header("Emissão em Lote")
    if st.button("Gerar Todos os XMLs do Dia"):
        hoje = datetime.now().date()
        vendas_df_fiscal['Data'] = pd.to_datetime(vendas_df_fiscal['Data'])
        vendas_do_dia = vendas_df_fiscal[(vendas_df_fiscal['Data'].dt.date == hoje)]
        if vendas_do_dia.empty:
            st.warning("Nenhuma venda registrada hoje para gerar os XMLs.")
        else:
            zip_buffer = BytesIO()
            with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
                for index, venda_info in vendas_do_dia.iterrows():
                    produto_info = st.session_state['df_produtos'][st.session_state['df_produtos']['Produto'] == venda_info['Produto']].copy()
                    if not produto_info.empty:
                        produto_info['Quantidade'] = venda_info['Quantidade']
                        xml_data = gerar_xml_nfc(venda_info, produto_info)
                        zip_file.writestr(f"nfce_{index}.xml", xml_data)
            st.download_button(label=f"Baixar {len(vendas_do_dia)} XMLs do Dia (.zip)", data=zip_buffer.getvalue(), file_name=f"XMLs_{hoje.strftime('%Y%m%d')}.zip", mime="application/zip")
    st.divider()
    st.subheader("Integração com Emissor Sebrae")
    st.markdown("""
    **Como funciona?**
    1.  **Gere o XML** (individual ou em lote) aqui no GMaster.
    2.  **Baixe o ficheiro** (ou o `.zip`) para o seu computador.
    3.  **Abra o seu Emissor Fiscal do Sebrae.**
    4.  No emissor, procure a opção **"Importar"** e selecione o(s) ficheiro(s) XML.
    5.  Verifique os dados e clique em **"Transmitir"** para assinar e enviar a nota.
    """)
    st.link_button("Abrir Site do Emissor Sebrae", "https://sebrae.com.br/sites/PortalSebrae/produtoseservicos/emissornfe")

with tab_empresa:
    st.header("⚙️ Dados da Empresa")
    st.info("Preencha e salve os dados da sua empresa. Serão utilizados na emissão de relatórios e documentos fiscais.")
    cfg = st.session_state['config_empresa']
    with st.form("form_empresa"):
        nome_fantasia = st.text_input("Nome Fantasia", value=cfg.get('nome_fantasia'))
        razao_social = st.text_input("Razão Social", value=cfg.get('razao_social'))
        cnpj = st.text_input("CNPJ", value=cfg.get('cnpj'))
        endereco = st.text_input("Endereço Completo", value=cfg.get('endereco'))
        cidade_uf = st.text_input("Cidade - UF", value=cfg.get('cidade_uf'))
        telefone = st.text_input("Telefone", value=cfg.get('telefone'))
        if st.form_submit_button("Salvar Dados da Empresa"):
            nova_config = {
                "nome_fantasia": nome_fantasia, "razao_social": razao_social, "cnpj": cnpj,
                "endereco": endereco, "cidade_uf": cidade_uf, "telefone": telefone
            }
            salvar_dados(nova_config, st.session_state['df_produtos'], st.session_state['df_estoque'], st.session_state['df_vendas'], st.session_state['df_compras'])
            st.rerun()

# --- Barra Lateral (COM BOTÃO DE ATUALIZAR) ---
st.sidebar.title("Opções")
if st.sidebar.button("Salvar TODAS as Alterações", type="primary", help="Salva todas as alterações feitas no cardápio, estoque e nome do restaurante."):
    salvar_dados(
        st.session_state['config_empresa'],
        st.session_state['df_produtos'].dropna(subset=['Produto']),
        st.session_state['df_estoque'],
        st.session_state['df_vendas'],
        st.session_state['df_compras']
    )
    st.rerun()

# NOVO: Botão para atualizar os gráficos manualmente
st.sidebar.divider()
if st.sidebar.button("🔄 Atualizar Gráficos", help="Recarrega os dados e atualiza os gráficos de análise."):
    st.rerun()

st.sidebar.divider()
st.sidebar.header("Exportar Dados")

def gerar_csv_powerbi(vendas_df, produtos_df):
    try:
        dados_combinados = pd.merge(vendas_df, produtos_df, on='Produto', how='left')
        return dados_combinados.to_csv(index=False).encode('utf-8')
    except Exception:
        return "".encode('utf-8')

st.sidebar.download_button(
    label="Exportar para Power BI (.csv)",
    data=gerar_csv_powerbi(st.session_state['df_vendas'], st.session_state['df_produtos']),
    file_name="dados_para_power_bi.csv",
    mime="text/csv",
    help="Exporta uma combinação das suas planilhas de Vendas e Cardápio."
)

sql_data = gerar_script_mysql(st.session_state['df_produtos'], st.session_state['df_estoque'], st.session_state['df_vendas'])
st.sidebar.download_button(
    label="Exportar para MySQL (.sql)",
    data=sql_data,
    file_name="backup.sql",
    mime="application/sql"
)