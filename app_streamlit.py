import streamlit as st
from dotenv import load_dotenv

from kers_assistant import (
    CatalogError,
    INSUFFICIENT_CONTEXT_MESSAGE,
    build_deepchat_prompt,
    generate_sales_answer,
    load_catalog,
    retrieve,
)

load_dotenv()

RESULT_COLUMNS = ["sku", "nome", "categoria", "codigo", "score", "status_dados"]

st.set_page_config(page_title="Assistente KERS", page_icon=":oncoming_automobile:", layout="wide")
st.title("Assistente de Vendas KERS")
st.caption("Versao profissional: base publica estruturada + resposta comercial local + DeepChat")

question = st.text_input(
    "Pergunta do vendedor",
    placeholder="Ex.: Qual politriz eu indico para acabamento em areas pequenas?",
)

col1, col2 = st.columns([2, 1])

if question:
    try:
        rows = retrieve(question, top_k=8, min_score=1)
    except CatalogError as exc:
        with col1:
            st.error(f"Erro ao carregar o catalogo: {exc}")
        with col2:
            st.info("Sem contexto disponivel enquanto o CSV nao for corrigido.")
    else:
        with col1:
            st.subheader("Resposta sugerida")
            if rows.empty:
                st.warning(INSUFFICIENT_CONTEXT_MESSAGE)
            else:
                with st.spinner("Buscando na base e montando resposta..."):
                    answer = generate_sales_answer(question, rows, response_style="full")
                st.write(answer)

                with st.expander("Prompt pronto para DeepChat"):
                    st.code(build_deepchat_prompt(question, rows), language="text")

        with col2:
            st.subheader("Contexto usado")
            if rows.empty:
                st.info("Nenhum item do catalogo atingiu correspondencia minima.")
            else:
                st.dataframe(rows[RESULT_COLUMNS], use_container_width=True)

with st.expander("Ver base carregada"):
    try:
        st.dataframe(load_catalog(), use_container_width=True)
    except CatalogError as exc:
        st.error(f"Erro ao carregar a base: {exc}")
