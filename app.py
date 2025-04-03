# 📦 Importações
from flask import Flask, request, jsonify, Response, send_from_directory
from dotenv import load_dotenv
from openai import OpenAI
from pathlib import Path
from io import BytesIO
import os
import requests

# 🚀 App Flask
app = Flask(__name__)

# 🔐 Variáveis de ambiente
load_dotenv()
openai_key = os.getenv("OPENAI_API_KEY")
whatsapp_token = os.getenv("WHATSAPP_TOKEN")
whatsapp_phone_id = os.getenv("WHATSAPP_PHONE_ID")
verify_token = os.getenv("VERIFY_TOKEN")

# 🤖 Cliente OpenAI
client = OpenAI(api_key=openai_key)

# 📁 Caminho do áudio
PASTA_AUDIO = Path("static/audio")
ARQUIVO_AUDIO = PASTA_AUDIO / "audio_ammozinho.mp3"
PASTA_AUDIO.mkdir(parents=True, exist_ok=True)

# 📄 Leitura de contexto e instruções
def carregar_arquivo(nome):
    caminho = Path("Templates") / nome
    return caminho.read_text(encoding="utf-8")

contexto = carregar_arquivo("contexto.txt")
instrucoes = carregar_arquivo("instrucoes_bot.txt")

# 🎙️ Transcrição do áudio
def transcrever_audio_whatsapp(audio_id):
    url = f"https://graph.facebook.com/v17.0/{audio_id}"
    headers = {"Authorization": f"Bearer {whatsapp_token}"}
    
    r = requests.get(url, headers=headers)
    audio_url = r.json().get("url")
    if not audio_url:
        print("❌ URL de áudio não encontrada.")
        return "Erro ao obter áudio."

    audio_response = requests.get(audio_url, headers=headers)
    audio_bytes = BytesIO(audio_response.content)
    audio_bytes.name = "audio.ogg"

    print("🎧 Enviando áudio para transcrição...")
    transcricao = client.audio.transcriptions.create(
        model="whisper-1",
        file=audio_bytes,
        response_format="text"
    )
    return transcricao

# 💬 Pergunta para OpenAI
def perguntar_openai(pergunta):
    resposta = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": instrucoes},
            {"role": "user", "content": f"Base de conhecimento:\n{contexto}"},
            {"role": "user", "content": pergunta}
        ],
        max_tokens=1000,
        temperature=0.5
    )
    return resposta.choices[0].message.content

# 🗣️ Gera áudio da resposta
def criar_audio_resposta(texto):
    if ARQUIVO_AUDIO.exists():
        ARQUIVO_AUDIO.unlink()
    resposta = client.audio.speech.create(
        model="tts-1",
        voice="nova",
        input=texto
    )
    resposta.write_to_file(ARQUIVO_AUDIO)
    print("🔊 Áudio salvo em:", ARQUIVO_AUDIO)

# 📤 Envia texto para WhatsApp
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
    print("📤 Texto enviado:", response.status_code, response.text)

# 📤 Envia áudio para WhatsApp
def enviar_audio(numero):
    audio_link = f"https://{request.host}/audio/{ARQUIVO_AUDIO.name}"
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
    print("📤 Áudio enviado:", response.status_code, response.text)

# 🔈 Servir áudio gerado
@app.route("/audio/<filename>")
def servir_audio(filename):
    return send_from_directory(PASTA_AUDIO, filename)

# 🌐 Webhook do WhatsApp
@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        mode = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")
        if mode == "subscribe" and token == verify_token:
            print("✅ Webhook verificado com sucesso.")
            return Response(challenge, status=200)
        return "Erro de verificação", 403

    if request.method == "POST":
        try:
            data = request.get_json()
            print("📨 Payload recebido:", data)

            value = data.get("entry", [{}])[0].get("changes", [{}])[0].get("value", {})
            mensagens = value.get("messages", [])
            if not mensagens:
                print("⚠️ Nenhuma mensagem encontrada.")
                return jsonify({"status": "sem mensagens"}), 200

            mensagem = mensagens[0]
            tipo = mensagem.get("type")
            numero = mensagem.get("from")

            print(f"💬 Mensagem recebida de {numero}, tipo: {tipo}")

            if tipo == "text":
                texto = mensagem.get("text", {}).get("body", "")
            elif tipo == "audio":
                audio_id = mensagem.get("audio", {}).get("id")
                texto = transcrever_audio_whatsapp(audio_id)
            else:
                texto = "Desculpe, só entendo mensagens de texto ou áudio."

            resposta = perguntar_openai(texto)
            enviar_texto(numero, resposta)
            criar_audio_resposta(resposta)
            enviar_audio(numero)

        except Exception as e:
            print("❌ Erro no processamento:", e)

        return jsonify({"status": "ok"}), 200

# ▶️ Início do servidor
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    app.run(host="0.0.0.0", port=port)
