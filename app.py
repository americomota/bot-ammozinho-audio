from flask import Flask, request, jsonify, Response, send_from_directory
import os
import requests
from dotenv import load_dotenv
from openai import OpenAI
from io import BytesIO
from pathlib import Path

app = Flask(__name__)
load_dotenv()

# Variáveis de ambiente
openai_key = os.getenv("OPENAI_API_KEY")
whatsapp_token = os.getenv("WHATSAPP_TOKEN")
whatsapp_phone_id = os.getenv("WHATSAPP_PHONE_ID")
verify_token = os.getenv("VERIFY_TOKEN")

client = OpenAI(api_key=openai_key)
ARQUIVO_AUDIO = "audio_ammozinho.mp3"

# Suporte

def carregar_arquivo(nome):
    with open(os.path.join("Templates", nome), "r", encoding="utf-8") as f:
        return f.read()

contexto = carregar_arquivo("contexto.txt")
instrucoes = carregar_arquivo("instrucoes_bot.txt")

def transcrever_audio_whatsapp(audio_id):
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

def criar_audio_resposta(texto):
    if Path(ARQUIVO_AUDIO).exists():
        Path(ARQUIVO_AUDIO).unlink()
    resposta = client.audio.speech.create(
        model="tts-1",
        voice="nova",
        input=texto
    )
    resposta.write_to_file(ARQUIVO_AUDIO)

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
    print("📤 Áudio enviado:", response.status_code, response.text)

@app.route("/audio/<filename>")
def servir_audio(filename):
    return send_from_directory(".", filename)

@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        mode = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")
        if mode == "subscribe" and token == verify_token:
            print("✅ Webhook verificado!")
            return Response(challenge, status=200)
        return "Erro na verificação", 403

    if request.method == "POST":
        data = request.get_json()
        print("📩 Mensagem recebida:", data)
        try:
            mensagem = data["entry"][0]["changes"][0]["value"]["messages"][0]
            tipo = mensagem["type"]
            numero = mensagem["from"]

            if tipo == "text":
                texto = mensagem["text"]["body"]
            elif tipo == "audio":
                audio_id = mensagem["audio"]["id"]
                texto = transcrever_audio_whatsapp(audio_id)
            else:
                texto = "Desculpe, só entendo texto e áudio por enquanto."

            resposta = perguntar_openai(texto)
            enviar_texto(numero, resposta)
            criar_audio_resposta(resposta)
            enviar_audio(numero)

        except Exception as e:
            print("❌ Erro ao processar mensagem:", e)
        return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    app.run(host="0.0.0.0", port=port)
