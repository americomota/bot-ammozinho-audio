import os
import uuid
import logging
from flask import Flask, request, jsonify, Response, send_from_directory
from dotenv import load_dotenv
from openai import OpenAI
import requests
from io import BytesIO
from pathlib import Path

# Inicializa o app Flask
app = Flask(__name__)

# Configura logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Carrega variáveis do .env
load_dotenv()

# Variáveis de ambiente
openai_key = os.getenv("OPENAI_API_KEY")
whatsapp_token = os.getenv("WHATSAPP_TOKEN")
whatsapp_phone_id = os.getenv("WHATSAPP_PHONE_ID")
verify_token = os.getenv("VERIFY_TOKEN")

# Inicializa cliente OpenAI
client = OpenAI(api_key=openai_key)

# Função para carregar textos do diretório Templates
def carregar_arquivo(nome):
    with open(os.path.join("Templates", nome), "r", encoding="utf-8") as f:
        return f.read()

contexto = carregar_arquivo("contexto.txt")
instrucoes = carregar_arquivo("instrucoes_bot.txt")

# Transcrição de áudio WhatsApp com Whisper
def transcrever_audio_whatsapp(audio_id):
    try:
        logger.info("🔊 Baixando áudio do WhatsApp...")
        url = f"https://graph.facebook.com/v17.0/{audio_id}"
        headers = {"Authorization": f"Bearer {whatsapp_token}"}

        r = requests.get(url, headers=headers)
        audio_url = r.json()["url"]
        audio_response = requests.get(audio_url, headers=headers)
        audio_bytes = BytesIO(audio_response.content)
        audio_bytes.name = "audio.ogg"

        logger.info("📝 Transcrevendo áudio com Whisper...")
        transcricao = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_bytes,
            response_format="text"
        )
        return transcricao
    except Exception as e:
        logger.error(f"❌ Erro ao transcrever áudio: {e}")
        return "Não consegui entender o áudio."

# Envia texto para OpenAI e recebe resposta
def perguntar_openai(pergunta):
    resposta = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": instrucoes},
            {"role": "user", "content": f"Base de conhecimento:\n{contexto}"},
            {"role": "user", "content": pergunta}
        ],
        max_tokens=1000,
        temperature=0
    )
    return resposta.choices[0].message.content

# Cria áudio com voz feminina da resposta do bot
def criar_audio_resposta(texto):
    try:
        filename = f"audio_{uuid.uuid4().hex}.mp3"
        logger.info("🎧 Gerando áudio com TTS da OpenAI...")
        resposta = client.audio.speech.create(
            model="tts-1",
            voice="nova",
            input=texto
        )
        resposta.write_to_file(filename)
        return filename
    except Exception as e:
        logger.error(f"❌ Erro ao criar áudio: {e}")
        return None

# Envia texto via WhatsApp
def enviar_texto(numero, mensagem):
    url = f"https://graph.facebook.com/v17.0/{whatsapp_phone_id}/messages"
    headers = {
        "Authorization": f"Bearer {whatsapp_token}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": numero,
        "type": "text",
        "text": {"body": mensagem}
    }
    response = requests.post(url, headers=headers, json=payload)
    logger.info(f"📤 Texto enviado: {response.status_code} - {response.text}")

# Envia áudio via WhatsApp com link do arquivo

def enviar_audio(numero, audio_filename):
    try:
        audio_link = f"https://{request.host}/audio/{audio_filename}"
        logger.info(f"📤 Enviando áudio com link: {audio_link}")

        url = f"https://graph.facebook.com/v17.0/{whatsapp_phone_id}/messages"
        headers = {
            "Authorization": f"Bearer {whatsapp_token}",
            "Content-Type": "application/json"
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": numero,
            "type": "audio",
            "audio": {"link": audio_link}
        }
        response = requests.post(url, headers=headers, json=payload)
        logger.info(f"📤 Áudio enviado: {response.status_code} - {response.text}")
    except Exception as e:
        logger.error(f"❌ Erro ao enviar áudio: {e}")

# Servidor de arquivos de áudio

@app.route("/audio/<filename>")
def servir_audio(filename):
    return send_from_directory(".", filename)

# Webhook do WhatsApp
@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        mode = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")
        if mode == "subscribe" and token == verify_token:
            logger.info("✅ Webhook verificado!")
            return Response(challenge, status=200)
        return "Erro na verificação", 403

    if request.method == "POST":
        data = request.get_json()
        logger.info(f"📩 Dados recebidos no webhook: {data}")

        try:
            value = data["entry"][0]["changes"][0]["value"]
            logger.info(f"📦 Conteúdo da mensagem: {value}")

            if "messages" in value:
                mensagem = value["messages"][0]
                tipo = mensagem["type"]
                numero = mensagem["from"]

                if tipo == "text":
                    texto = mensagem["text"]["body"]
                elif tipo == "audio":
                    audio_id = mensagem["audio"]["id"]
                    texto = transcrever_audio_whatsapp(audio_id)
                else:
                    texto = "Desculpe, só entendo texto e áudio por enquanto."

                logger.info(f"💬 Pergunta recebida: {texto}")
                resposta = perguntar_openai(texto)
                logger.info(f"🤖 Resposta da IA: {resposta}")
                enviar_texto(numero, resposta)
                audio_file = criar_audio_resposta(resposta)
                if audio_file:
                    enviar_audio(numero, audio_file)
            else:
                logger.warning("⚠️ Nenhuma mensagem encontrada no payload.")

        except Exception as e:
            logger.error(f"❌ Erro ao processar mensagem: {e}")

        return jsonify({"status": "ok"}), 200

# Inicia o servidor
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    app.run(host="0.0.0.0", port=port)
