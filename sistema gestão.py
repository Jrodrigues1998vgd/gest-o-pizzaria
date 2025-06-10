import streamlit as st
import pandas as pd
import plotly.express as px
from fpdf import FPDF
import os
from datetime import datetime
from io import BytesIO
import xml.etree.ElementTree as ET
from xml.dom import minidom

# --- Configuração da Página ---
st.set_page_config(
    page_title="Gestão de Pizzaria - GMaster",
    page_icon="🍕",
    layout="wide"
)

# --- Estilo CSS Personalizado ---
st.markdown("""
<style>
    .stApp { background-color: #f0f2f6; }
    h2 { color: #b71c1c; font-weight: bold; }
    .stButton>button {
        background-color: #ffc107; color: black; border-radius: 8px;
        border: none; padding: 10px 20px; font-weight: bold;
    }
    .stButton>button:hover { background-color: #ffa000; }
</style>
""", unsafe_allow_html=True)

# --- Funções de Manipulação de Dados ---
DB_FILE = "pizzaria_db.xlsx"

def carregar_dados():
    try:
        with open(DB_FILE, 'rb') as f:
            xls = pd.ExcelFile(f)
            df_produtos = pd.read_excel(xls, 'Cardapio')
            df_estoque = pd.read_excel(xls, 'Estoque')
            df_vendas = pd.read_excel(xls, 'Vendas')
        
        with open("config.txt", "r", encoding="utf-8") as f:
            nome_restaurante = f.read().strip()
    except FileNotFoundError:
        return None, None, None, "Pizzaria Casa Velha"
    except Exception as e:
        st.error(f"Erro ao ler os arquivos: {e}")
        return None, None, None, "Pizzaria Casa Velha"
        
    return df_produtos, df_estoque, df_vendas, nome_restaurante

def salvar_dados(nome_restaurante, produtos, estoque, vendas):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        produtos.to_excel(writer, index=False, sheet_name='Cardapio')
        estoque.to_excel(writer, index=False, sheet_name='Estoque')
        vendas.to_excel(writer, index=False, sheet_name='Vendas')
    
    with open(DB_FILE, "wb") as f:
        f.write(output.getvalue())

    with open("config.txt", "w", encoding="utf-8") as f:
        f.write(nome_restaurante)
    
    st.success("🎉 Dados salvos com sucesso!")

def criar_db_modelo():
    df_produtos = pd.DataFrame(columns=['Produto', 'Categoria', 'Preco_Venda', 'Custo_Unitario'])
    df_estoque = pd.DataFrame(columns=['Produto', 'Quantidade_Estoque'])
    df_vendas = pd.DataFrame(columns=['Data', 'Produto', 'Quantidade', 'CPF_Cliente'])
    
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_produtos.to_excel(writer, index=False, sheet_name='Cardapio')
        df_estoque.to_excel(writer, index=False, sheet_name='Estoque')
        df_vendas.to_excel(writer, index=False, sheet_name='Vendas')
    
    return output.getvalue()

# --- Funções de Exportação e Fiscal ---
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
    ET.SubElement(emit, "CNPJ").text = "00000000000191"
    ET.SubElement(emit, "xNome").text = st.session_state['nome_restaurante']
    
    if 'CPF_Cliente' in venda_info and pd.notna(venda_info['CPF_Cliente']):
        dest = ET.SubElement(infNFe, "dest")
        ET.SubElement(dest, "CPF").text = str(venda_info['CPF_Cliente'])

    total_nota = 0
    for index, row in produtos_info.iterrows():
        det = ET.SubElement(infNFe, "det", nItem=str(index + 1))
        prod = ET.SubElement(det, "prod")
        ET.SubElement(prod, "cProd").text = f"P{index+1}"
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

def gerar_csv_powerbi(df_vendas_detalhado):
    return df_vendas_detalhado.to_csv(index=False).encode('utf-8')

def gerar_script_mysql(produtos, estoque, vendas):
    sql_script = ""
    sql_script += "DROP TABLE IF EXISTS `cardapio`;\n"
    sql_script += "CREATE TABLE `cardapio` (`Produto` varchar(255) NOT NULL, `Categoria` varchar(255) DEFAULT NULL, `Preco_Venda` decimal(10,2) DEFAULT NULL, `Custo_Unitario` decimal(10,2) DEFAULT NULL, PRIMARY KEY (`Produto`)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;\n\n"
    if not produtos.empty:
        for index, row in produtos.iterrows():
            sql_script += f"INSERT INTO `cardapio` VALUES ('{str(row.get('Produto','')).replace(\"'\", \"''\")}', '{str(row.get('Categoria',''))}', {row.get('Preco_Venda', 0)}, {row.get('Custo_Unitario', 0)});\n"
    
    sql_script += "\nDROP TABLE IF EXISTS `estoque`;\n"
    sql_script += "CREATE TABLE `estoque` (`Produto` varchar(255) NOT NULL, `Quantidade_Estoque` int(11) DEFAULT NULL, PRIMARY KEY (`Produto`)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;\n\n"
    if not estoque.empty:
        for index, row in estoque.iterrows():
            sql_script += f"INSERT INTO `estoque` VALUES ('{str(row.get('Produto','')).replace(\"'\", \"''\")}', {row.get('Quantidade_Estoque', 0)});\n"

    sql_script += "\nDROP TABLE IF EXISTS `vendas`;\n"
    sql_script += "CREATE TABLE `vendas` (`id` int(11) NOT NULL AUTO_INCREMENT, `Data` datetime DEFAULT NULL, `Produto` varchar(255) DEFAULT NULL, `Quantidade` int(11) DEFAULT NULL, `CPF_Cliente` varchar(20) DEFAULT NULL, PRIMARY KEY (`id`)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;\n\n"
    if not vendas.empty:
        for index, row in vendas.iterrows():
            cpf = str(row.get('CPF_Cliente', '')).replace("'", "''")
            sql_script += f"INSERT INTO `vendas` (`Data`, `Produto`, `Quantidade`, `CPF_Cliente`) VALUES ('{pd.to_datetime(row.get('Data')).strftime('%Y-%m-%d %H:%M:%S')}', '{str(row.get('Produto','')).replace(\"'\", \"''\")}', {row.get('Quantidade', 0)}, '{cpf}');\n"
    return sql_script.encode('utf-8')

def gerar_relatorio_pdf(df_vendas_filtrado, nome_restaurante):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, f'Relatório de Vendas - {nome_restaurante}', 0, 1, 'C')
    pdf.ln(10)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(40, 10, 'Data', 1)
    pdf.cell(80, 10, 'Produto', 1)
    pdf.cell(30, 10, 'Quantidade', 1)
    pdf.cell(30, 10, 'Receita', 1)
    pdf.ln()
    pdf.set_font("Arial", '', 12)
    for index, row in df_vendas_filtrado.iterrows():
        pdf.cell(40, 10, str(row['Data'].date()), 1)
        pdf.cell(80, 10, row['Produto'], 1)
        pdf.cell(30, 10, str(row['Quantidade']), 1)
        pdf.cell(30, 10, f"R${row.get('Receita', 0):.2f}", 1)
        pdf.ln()
    nome_arquivo = f"Relatorio_Vendas_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    pdf.output(nome_arquivo)
    return nome_arquivo

# --- Interface Principal ---
if not os.path.exists(DB_FILE):
    st.warning("⚠️ Arquivo de base de dados (pizzaria_db.xlsx) não encontrado.")
    st.info("Para começar, crie um arquivo de base de dados modelo. Salve-o na mesma pasta que este programa.")
    st.download_button("Criar e Baixar Base de Dados Modelo", data=criar_db_modelo(), file_name=DB_FILE)
    st.stop()

if 'dados_carregados' not in st.session_state:
    df_produtos, df_estoque, df_vendas, nome_restaurante = carregar_dados()
    if df_produtos is None:
        st.error("Falha ao carregar os dados. Reinicie a página e verifique o arquivo 'pizzaria_db.xlsx'.")
        st.stop()
    st.session_state['nome_restaurante'] = nome_restaurante
    st.session_state['df_produtos'] = df_produtos
    st.session_state['df_estoque'] = df_estoque
    st.session_state['df_vendas'] = df_vendas
    st.session_state['dados_carregados'] = True

st.title(f"🍕 {st.session_state['nome_restaurante']} - GMaster")
tab_dashboard, tab_vendas, tab_cardapio, tab_estoque, tab_fiscal = st.tabs(["📊 Dashboard", "💰 Registrar Venda", "📖 Cardápio", "📦 Estoque", "🧾 Emissão Fiscal"])

with tab_dashboard:
    st.header("Análise de Desempenho")
    vendas_df = st.session_state.get('df_vendas', pd.DataFrame())
    produtos_df = st.session_state.get('df_produtos', pd.DataFrame())
    vendas_detalhadas = pd.DataFrame()
    if not vendas_df.empty and not produtos_df.empty:
        vendas_detalhadas = pd.merge(vendas_df, produtos_df, on='Produto', how='left').dropna(subset=['Preco_Venda', 'Custo_Unitario'])
        if not vendas_detalhadas.empty:
            vendas_detalhadas['Receita'] = vendas_detalhadas['Quantidade'] * vendas_detalhadas['Preco_Venda']
            vendas_detalhadas['Lucro'] = vendas_detalhadas['Receita'] - (vendas_detalhadas['Quantidade'] * vendas_detalhadas['Custo_Unitario'])
            vendas_detalhadas['Data'] = pd.to_datetime(vendas_detalhadas['Data'])
    
    data_inicio = pd.to_datetime(st.date_input("Data de Início", vendas_detalhadas['Data'].min().date() if not vendas_detalhadas.empty else datetime.now().date()))
    data_fim = pd.to_datetime(st.date_input("Data de Fim", vendas_detalhadas['Data'].max().date() if not vendas_detalhadas.empty else datetime.now().date()))
    vendas_filtradas = vendas_detalhadas[(vendas_detalhadas['Data'] >= data_inicio) & (vendas_detalhadas['Data'] <= data_fim)] if not vendas_detalhadas.empty else pd.DataFrame()

    kpi1, kpi2, kpi3 = st.columns(3)
    kpi1.metric("Receita Total", f"R$ {vendas_filtradas['Receita'].sum():.2f}" if not vendas_filtradas.empty else "R$ 0.00")
    kpi2.metric("Lucro Total", f"R$ {vendas_filtradas['Lucro'].sum():.2f}" if not vendas_filtradas.empty else "R$ 0.00")
    kpi3.metric("Total de Itens Vendidos", f"{vendas_filtradas['Quantidade'].sum()}" if not vendas_filtradas.empty else "0")

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
        
    if st.button("Gerar Relatório de Vendas em PDF"):
        if not vendas_filtradas.empty:
            nome_arquivo_pdf = gerar_relatorio_pdf(vendas_filtradas, st.session_state['nome_restaurante'])
            with open(nome_arquivo_pdf, "rb") as file:
                st.download_button(label="Baixar Relatório PDF", data=file, file_name=nome_arquivo_pdf, mime="application/octet-stream")
            os.remove(nome_arquivo_pdf)
        else:
            st.warning("Nenhuma venda no período selecionado.")

with tab_vendas:
    st.header("Registrar Nova Venda")
    produtos_disponiveis = st.session_state['df_produtos']['Produto'].tolist() if not st.session_state['df_produtos'].empty else []
    if produtos_disponiveis:
        produto_vendido = st.selectbox("Selecione o Produto", options=produtos_disponiveis, key="venda_produto")
        quantidade_vendida = st.number_input("Quantidade", min_value=1, step=1, key="venda_qtde")
        cpf_cliente = st.text_input("CPF do Cliente (Opcional)", key="venda_cpf")
        
        if st.button("Confirmar Venda"):
            idx_estoque = st.session_state['df_estoque'].index[st.session_state['df_estoque']['Produto'] == produto_vendido].tolist()
            if idx_estoque:
                estoque_atual = st.session_state['df_estoque'].loc[idx_estoque[0], 'Quantidade_Estoque']
                if estoque_atual >= quantidade_vendida:
                    st.session_state['df_estoque'].loc[idx_estoque[0], 'Quantidade_Estoque'] -= quantidade_vendida
                    nova_venda = pd.DataFrame([{'Data': datetime.now(), 'Produto': produto_vendido, 'Quantidade': quantidade_vendida, 'CPF_Cliente': cpf_cliente}])
                    st.session_state['df_vendas'] = pd.concat([st.session_state['df_vendas'], nova_venda], ignore_index=True)
                    st.success("Venda registrada com sucesso!")
                else:
                    st.error(f"Estoque insuficiente! Apenas {estoque_atual} unidade(s) disponível(is).")
            else:
                st.error("Produto sem registro no estoque! Adicione-o na aba Estoque.")
    else:
        st.warning("Adicione produtos no Cardápio para começar a registrar vendas.")

with tab_cardapio:
    st.header("Gerenciar Cardápio (Produtos)")
    st.info("Clique duas vezes numa célula para editar. Adicione ou remova linhas usando os botões `+` e `x` na parte inferior da tabela.")
    st.session_state['df_produtos'] = st.data_editor(st.session_state['df_produtos'], num_rows="dynamic", key="editor_produtos")

with tab_estoque:
    st.header("Controlar Estoque")
    produtos_no_cardapio = st.session_state['df_produtos']['Produto'].unique()
    estoque_atual_df = st.session_state['df_estoque']
    
    # Sincronizar estoque: remove produtos que não estão mais no cardápio e adiciona novos
    estoque_sincronizado = estoque_atual_df[estoque_atual_df['Produto'].isin(produtos_no_cardapio)]
    novos_produtos = [p for p in produtos_no_cardapio if p not in estoque_sincronizado['Produto'].values]
    if novos_produtos:
        novos_estoque_df = pd.DataFrame({'Produto': novos_produtos, 'Quantidade_Estoque': [0]*len(novos_produtos)})
        estoque_sincronizado = pd.concat([estoque_sincronizado, novos_estoque_df], ignore_index=True)
    
    st.info("A lista de produtos é sincronizada com o Cardápio. Apenas a quantidade pode ser editada aqui.")
    st.session_state['df_estoque'] = st.data_editor(estoque_sincronizado, disabled=['Produto'], key="editor_estoque")

with tab_fiscal:
    st.header("Gerar XML para Emissão Fiscal")
    st.info("Selecione uma venda para gerar o arquivo XML. Este arquivo pode ser importado em seu emissor fiscal de desktop para assinar e transmitir a NFC-e.")
    vendas_df_fiscal = st.session_state['df_vendas']
    if not vendas_df_fiscal.empty:
        vendas_recentes = vendas_df_fiscal.tail(10).sort_index(ascending=False)
        vendas_recentes['display'] = vendas_recentes.apply(lambda row: f"ID {row.name} - {row['Produto']} ({row['Quantidade']}x) - {pd.to_datetime(row['Data']).strftime('%d/%m/%Y %H:%M')}", axis=1)
        venda_selecionada_display = st.selectbox("Selecione uma Venda Recente", options=vendas_recentes['display'])
        if venda_selecionada_display:
            venda_id = int(venda_selecionada_display.split(" ")[1])
            venda_info = vendas_df_fiscal.loc[venda_id]
            produto_info = st.session_state['df_produtos'][st.session_state['df_produtos']['Produto'] == venda_info['Produto']].copy()
            produto_info['Quantidade'] = venda_info['Quantidade']
            
            st.write("Detalhes da Venda Selecionada:")
            st.dataframe(pd.DataFrame([venda_info]))
            if st.button("Gerar XML da NFC-e"):
                xml_data = gerar_xml_nfc(venda_info, produto_info)
                st.download_button(label="Baixar XML para Emissão", data=xml_data, file_name=f"nfce_{venda_id}.xml", mime="application/xml")
    else:
        st.warning("Nenhuma venda registrada para gerar XML.")

# --- Barra Lateral ---
st.sidebar.title("Opções")
st.session_state['nome_restaurante'] = st.sidebar.text_input("Nome do Restaurante", value=st.session_state.get('nome_restaurante'))
if st.sidebar.button("Salvar Todas as Alterações", type="primary"):
    salvar_dados(
        st.session_state['nome_restaurante'],
        st.session_state['df_produtos'].dropna(subset=['Produto']),
        st.session_state['df_estoque'],
        st.session_state['df_vendas']
    )
st.sidebar.divider()
st.sidebar.header("Exportar Dados")

if not vendas_detalhadas.empty:
    csv_data = gerar_csv_powerbi(vendas_detalhadas)
    st.sidebar.download_button("Exportar para Power BI (.csv)", data=csv_data, file_name="dados_para_power_bi.csv", mime="text/csv")

sql_data = gerar_script_mysql(st.session_state['df_produtos'], st.session_state['df_estoque'], st.session_state['df_vendas'])
st.sidebar.download_button("Exportar para MySQL (.sql)", data=sql_data, file_name="backup.sql", mime="application/sql")
