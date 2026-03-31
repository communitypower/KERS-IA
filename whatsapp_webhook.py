from dotenv import load_dotenv
from flask import Flask, Response, request
from twilio.twiml.messaging_response import MessagingResponse

from kers_assistant import CatalogError, INSUFFICIENT_CONTEXT_MESSAGE, generate_sales_answer, retrieve

load_dotenv()

app = Flask(__name__)


def whatsapp_message(body: str) -> str:
    if not body:
        return "Envie sua pergunta sobre um produto KERS."

    try:
        rows = retrieve(body, top_k=6, min_score=1)
    except CatalogError:
        return "Nao consegui acessar a base da KERS agora. Verifique o CSV configurado."

    if rows.empty:
        return INSUFFICIENT_CONTEXT_MESSAGE

    return generate_sales_answer(body, rows, response_style="whatsapp")[:1500]


@app.post("/webhook/whatsapp")
def whatsapp_webhook():
    incoming_msg = (request.form.get("Body") or "").strip()
    twiml = MessagingResponse()
    twiml.message(whatsapp_message(incoming_msg))
    return Response(str(twiml), mimetype="application/xml")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
