from dotenv import load_dotenv
from flask import Flask, Response, request
from twilio.twiml.messaging_response import MessagingResponse

from kers_assistant import (
    CatalogError,
    INSUFFICIENT_CONTEXT_MESSAGE,
    LLMConfigurationError,
    LLMResponseError,
    ask_llm,
    build_context,
    retrieve,
)

load_dotenv()

app = Flask(__name__)

SYSTEM_PROMPT = """
Voce e um assistente de vendas da KERS para representantes, vendedores de balcao e lojistas.
Responda de forma objetiva para WhatsApp, usando somente o contexto enviado.
Estruture em:
- Produto recomendado
- Por que
- Como vender
- Objecao
- Venda adicional
Se o contexto for insuficiente, diga isso claramente.
""".strip()


def whatsapp_message(body: str) -> str:
    if not body:
        return "Envie sua pergunta sobre um produto KERS."

    try:
        rows = retrieve(body, top_k=6, min_score=1)
        context = build_context(rows)
    except CatalogError:
        return "Nao consegui acessar a base da KERS agora. Verifique o CSV configurado."

    if rows.empty:
        return INSUFFICIENT_CONTEXT_MESSAGE

    try:
        answer = ask_llm(body, context, SYSTEM_PROMPT)
    except LLMConfigurationError as exc:
        return str(exc)
    except LLMResponseError:
        return "Nao consegui gerar a resposta agora. Tente novamente em instantes."

    return answer[:1500]


@app.post("/webhook/whatsapp")
def whatsapp_webhook():
    incoming_msg = (request.form.get("Body") or "").strip()
    twiml = MessagingResponse()
    twiml.message(whatsapp_message(incoming_msg))
    return Response(str(twiml), mimetype="application/xml")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
