# KERS - versao full profissional

Base publica estruturada + app web em Streamlit + webhook WhatsApp + agente ACP para DeepChat.

## Conteudo
- `kers_base_profissional_publica.csv`
- `kers_base_profissional_publica.xlsx`
- `app_streamlit.py`
- `whatsapp_webhook.py`
- `kers_assistant.py`
- `kers_deepchat_acp.py`
- `run_kers_deepchat_agent.ps1`
- `requirements.txt`
- `.env.example`

## O que esta versao entrega
- Base publica estruturada com SKUs reais extraidos das paginas publicas da KERS.
- Camada comercial pronta para apoio ao representante sem depender de OpenAI.
- App web em Streamlit.
- Webhook WhatsApp em Flask/Twilio.
- Agente ACP para rodar dentro do DeepChat.
- Fonte do dado em coluna separada.
- Tratamento mais seguro para falta de contexto e erro de CSV.

## Instalacao
```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
```

Se `python` ou `pip` abrirem o alias da Microsoft Store no Windows, instale uma distribuicao real do Python e tente novamente.

## Variaveis de ambiente
Copie `.env.example` para `.env` se quiser apontar para outro CSV.

```bash
copy .env.example .env
```

## Rodar o app web
```bash
streamlit run app_streamlit.py
```

## Rodar o webhook WhatsApp
```bash
python whatsapp_webhook.py
```

## Integracao com DeepChat
O projeto agora inclui um agente ACP pronto para o DeepChat.

### Opcao recomendada no Windows
No DeepChat, crie um agente ACP customizado com:
- `command`: `C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe`
- `args`: `-ExecutionPolicy`, `Bypass`, `-File`, `c:\Users\PC\kers_full_professional\run_kers_deepchat_agent.ps1`
- `workdir`: `c:\Users\PC\kers_full_professional`

Se a `.venv` tiver sido criada em cima do alias da Microsoft Store, recrie o ambiente com um Python real antes de usar o agente ACP.

### Opcao direta com Python
Se preferir, rode o agente manualmente:

```bash
python kers_deepchat_acp.py
```

## Conectar com o WhatsApp via Twilio
Configure o webhook do seu sandbox ou numero oficial para:

`https://SEU_DOMINIO/webhook/whatsapp`

## Limite desta base
Esta base usa apenas as paginas publicas abertas do site.
Para virar catalogo operacional 100% completo, o proximo passo e enriquecer com:
- preco
- margem
- estoque
- concorrente equivalente
- FAQ real do time comercial
- PDFs e manuais tecnicos

## Proximo passo recomendado
Rodar um piloto com 3 vendedores por 7 dias e registrar:
- perguntas sem resposta
- produtos com busca recorrente
- objecoes mais frequentes
