# 📦 Importa os pacotes necessários
from flask import Flask, request, jsonify, Response, send_from_directory
import os
import requests
from dotenv import load_dotenv
from openai import OpenAI
from io import BytesIO
from pathlib import Path
import logging

# 🛠️ Configuração do logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 🚀 Cria a aplicação Flask
app = Flask(__name__)
load_dotenv()

# 🔒 Variáveis de ambiente
openai_key = os.getenv("OPENAI_API_KEY")
whatsapp_token = os.getenv("WHATSAPP_TOKEN")
whatsapp_phone_id = os.getenv("WHATSAPP_PHONE_ID")
verify_token = os.getenv("VERIFY_TOKEN")

# 🤖 Cliente da OpenAI
client = OpenAI(api_key=openai_key)

# 📁 Nome padrão do arquivo de áudio gerado
ARQUIVO_AUDIO = "audio_ammozinho.mp3"

# 📄 Função para carregar arquivos de texto do diretório Templates
def carregar_arquivo(nome):
    caminho = os.path.join("Templates", nome)
    if not os.path.exists(caminho):
        logger.error(f"Arquivo não encontrado: {caminho}")
        return ""
    with open(caminho, "r", encoding="utf-8") as f:
        return f.read()

# 📚 Carrega o contexto e instruções do bot
contexto = carregar_arquivo("contexto.txt")
instrucoes = carregar_arquivo("instrucoes_bot.txt")

# 🎙️ Transcreve áudios enviados pelo WhatsApp usando o Whisper da OpenAI
def transcrever_audio_whatsapp(audio_id):
    try:
        url = f"https://graph.facebook.com/v17.0/{audio_id}"
        headers = {"Authorization": f"Bearer {whatsapp_token}"}

        r = requests.get(url, headers=headers)
        audio_url = r.json()["url"]
        audio_response = requests.get(audio_url, headers=headers)
        audio_bytes = BytesIO(audio_response.content)
        audio_bytes.name = "audio.ogg"

        transcricao = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_bytes,
            response_format="text"
        )
        return transcricao
    except Exception as e:
        logger.error("Erro na transcrição de áudio: %s", e)
        return "Desculpe, não consegui entender o áudio."

# 💬 Envia a pergunta para o ChatGPT (gpt-3.5-turbo) e retorna a resposta
def perguntar_openai(pergunta):
    try:
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
    except Exception as e:
        logger.error("Erro ao perguntar para o ChatGPT: %s", e)
        return "Houve um erro ao consultar a IA. Tente novamente."

# 🔊 Gera áudio da resposta do bot com voz da OpenAI
def criar_audio_resposta(texto):
    try:
        if Path(ARQUIVO_AUDIO).exists():
            Path(ARQUIVO_AUDIO).unlink()
        resposta = client.audio.speech.create(
            model="tts-1",
            voice="nova",
            input=texto
        )
        resposta.write_to_file(ARQUIVO_AUDIO)
    except Exception as e:
        logger.error("Erro ao gerar áudio com TTS: %s", e)

# 📤 Envia mensagem de texto via WhatsApp
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
    logger.info("📤 Texto enviado: %s - %s", response.status_code, response.text)

# 📤 Envia o áudio gerado para o número do usuário
def enviar_audio(numero):
    audio_link = f"https://{request.host}/audio/{ARQUIVO_AUDIO}"
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
    logger.info("📤 Áudio enviado: %s - %s", response.status_code, response.text)

# 🎧 Rota para servir o arquivo de áudio
@app.route("/audio/<filename>")
def servir_audio(filename):
    return send_from_directory(".", filename)

# 🌐 Rota principal do webhook do WhatsApp
@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        mode = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")
        if mode == "subscribe" and token == verify_token:
            logger.info("✅ Webhook verificado com sucesso.")
            return Response(challenge, status=200)
        return "Erro na verificação", 403

    if request.method == "POST":
        data = request.get_json()
        logger.info("📩 Dados recebidos no webhook: %s", data)

        try:
            value = data["entry"][0]["changes"][0]["value"]
            logger.info("📦 Conteúdo da mensagem: %s", value)

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

                logger.info("💬 Pergunta recebida: %s", texto)
                resposta = perguntar_openai(texto)
                logger.info("🤖 Resposta da IA: %s", resposta)

                enviar_texto(numero, resposta)
                criar_audio_resposta(resposta)
                enviar_audio(numero)
            else:
                logger.warning("⚠️ Nenhuma mensagem encontrada no payload.")

        except Exception as e:
            logger.exception("❌ Erro ao processar webhook:")

        return jsonify({"status": "ok"}), 200

# 🚀 Inicia o servidor Flask
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    app.run(host="0.0.0.0", port=port)
