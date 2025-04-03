# 📦 Importa os pacotes necessários
from flask import Flask, request, jsonify, Response, send_from_directory
import os
import requests
from dotenv import load_dotenv
from openai import OpenAI
from io import BytesIO
from pathlib import Path
import logging

# 🔧 Configura o log para aparecer no Render
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 🚀 Cria a aplicação Flask
app = Flask(__name__)

# 🔒 Carrega as variáveis do arquivo .env
load_dotenv()

# 🌍 Variáveis de ambiente
openai_key = os.getenv("OPENAI_API_KEY")
whatsapp_token = os.getenv("WHATSAPP_TOKEN")
whatsapp_phone_id = os.getenv("WHATSAPP_PHONE_ID")
verify_token = os.getenv("VERIFY_TOKEN")

# 🤖 Cliente da OpenAI
client = OpenAI(api_key=openai_key)

# 📁 Nome do arquivo de áudio que será criado
ARQUIVO_AUDIO = "audio_ammozinho.mp3"

# 📄 Função para carregar arquivos de texto
def carregar_arquivo(nome):
    with open(os.path.join("Templates", nome), "r", encoding="utf-8") as f:
        return f.read()

# 📚 Carrega os arquivos de contexto e instruções do bot
contexto = carregar_arquivo("contexto.txt")
instrucoes = carregar_arquivo("instrucoes_bot.txt")

# 🎙️ Função para transcrever o áudio recebido do WhatsApp
def transcrever_audio_whatsapp(audio_id):
    url = f"https://graph.facebook.com/v17.0/{audio_id}"
    headers = {"Authorization": f"Bearer {whatsapp_token}"}

    logger.info("🔊 Baixando áudio do WhatsApp...")
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

# 💬 Função para consultar o ChatGPT
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

# 🔊 Função para criar o áudio da resposta
def criar_audio_resposta(texto):
    if Path(ARQUIVO_AUDIO).exists():
        Path(ARQUIVO_AUDIO).unlink()
    logger.info("🎧 Gerando áudio com TTS da OpenAI...")
    resposta = client.audio.speech.create(
        model="tts-1",
        voice="nova",
        input=texto
    )
    resposta.write_to_file(ARQUIVO_AUDIO)

# 📤 Função para enviar mensagem de texto pelo WhatsApp
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

# 📤 Função para enviar áudio pelo WhatsApp
def enviar_audio(numero):
    url = f"https://graph.facebook.com/v17.0/{whatsapp_phone_id}/messages"
    headers = {
        "Authorization": f"Bearer {whatsapp_token}",
        "Content-Type": "application/json"
    }
    audio_link = f"https://{request.host}/audio/{ARQUIVO_AUDIO}"
    payload = {
        "messaging_product": "whatsapp",
        "to": numero,
        "type": "audio",
        "audio": {"link": audio_link}
    }
    response = requests.post(url, headers=headers, json=payload)
    logger.info(f"📤 Áudio enviado: {response.status_code} - {response.text}")

# 🎧 Rota para servir o arquivo de áudio (link público)
@app.route("/audio/<filename>")
def servir_audio(filename):
    return send_from_directory(".", filename)

# 🌐 Webhook principal (verificação + recebimento)
@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        mode = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")
        if mode == "subscribe" and token == verify_token:
            logger.info("✅ Webhook verificado com sucesso!")
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
                criar_audio_resposta(resposta)  # ✅ corrigido aqui
                enviar_audio(numero)

            else:
                logger.warning("⚠️ Nenhuma mensagem encontrada no payload.")

        except Exception as e:
            logger.error(f"❌ Erro ao processar mensagem: {e}")

        return jsonify({"status": "ok"}), 200

# 🚀 Inicia o servidor Flask (porta do Render)
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    app.run(host="0.0.0.0", port=port)
