import streamlit as st
from dotenv import load_dotenv

from kers_assistant import (
    CatalogError,
    INSUFFICIENT_CONTEXT_MESSAGE,
    LLMConfigurationError,
    LLMResponseError,
    ask_llm,
    build_context,
    load_catalog,
    retrieve,
)

load_dotenv()

SYSTEM_PROMPT = """
Voce e um assistente de vendas da KERS para representantes, vendedores de balcao e lojistas.

Regras:
1. Use somente o contexto fornecido.
2. Se faltarem dados, diga explicitamente que o contexto publico nao basta.
3. Estruture em:
   - Produto recomendado
   - Justificativa tecnica
   - Como vender
   - Objecao comum
   - Resposta a objecao
   - Venda adicional
4. Nao invente especificacoes.
5. Responda em portugues do Brasil.
""".strip()

RESULT_COLUMNS = ["sku", "nome", "categoria", "codigo", "score", "status_dados"]

st.set_page_config(page_title="Assistente KERS", page_icon=":oncoming_automobile:", layout="wide")
st.title("Assistente de Vendas KERS")
st.caption("Versao profissional: base publica estruturada + resposta com OpenAI")

question = st.text_input(
    "Pergunta do vendedor",
    placeholder="Ex.: Qual politriz eu indico para acabamento em areas pequenas?",
)

col1, col2 = st.columns([2, 1])

if question:
    try:
        rows = retrieve(question, top_k=8, min_score=1)
        context = build_context(rows)
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
                try:
                    with st.spinner("Consultando base e gerando resposta..."):
                        answer = ask_llm(question, context, SYSTEM_PROMPT)
                except LLMConfigurationError as exc:
                    st.info(str(exc))
                except LLMResponseError as exc:
                    st.error(str(exc))
                else:
                    st.write(answer)

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
