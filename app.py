# 📦 Importa os pacotes necessários
from flask import Flask, request, jsonify, Response, send_from_directory
import os
import requests
from dotenv import load_dotenv
from openai import OpenAI
from io import BytesIO
from pathlib import Path

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

# 📁 Nome padrão do arquivo de áudio gerado
ARQUIVO_AUDIO = "audio_ammozinho.mp3"

# 📄 Função para carregar arquivos de texto do diretório Templates
def carregar_arquivo(nome):
    with open(os.path.join("Templates", nome), "r", encoding="utf-8") as f:
        return f.read()

# 📚 Carrega o contexto e instruções do bot
contexto = carregar_arquivo("contexto.txt")
instrucoes = carregar_arquivo("instrucoes_bot.txt")

# 🎙️ Transcreve áudios enviados pelo WhatsApp usando o Whisper da OpenAI
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

# 💬 Envia a pergunta para o ChatGPT (gpt-3.5-turbo) e retorna a resposta
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

# 🔊 Gera áudio da resposta do bot com voz da OpenAI
def criar_audio_resposta(texto):
    if Path(ARQUIVO_AUDIO).exists():
        Path(ARQUIVO_AUDIO).unlink()  # Apaga arquivo antigo, se existir
    resposta = client.audio.speech.create(
        model="tts-1",
        voice="nova",
        input=texto
    )
    resposta.write_to_file(ARQUIVO_AUDIO)

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
    print("📤 Texto enviado:", response.status_code, response.text)

# 📤 Envia o áudio gerado para o número do usuário
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

# 🎧 Rota para servir o arquivo de áudio
@app.route("/audio/<filename>")
def servir_audio(filename):
    return send_from_directory(".", filename)

# 🌐 Rota principal do webhook do WhatsApp
@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        # Verificação do webhook pelo Meta (WhatsApp)
        mode = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")
        if mode == "subscribe" and token == verify_token:
            print("✅ Webhook verificado!")
            return Response(challenge, status=200)
        return "Erro na verificação", 403

    if request.method == "POST":
        data = request.get_json()
        print("📩 Dados recebidos no webhook:", data)

        try:
            value = data["entry"][0]["changes"][0]["value"]
            print("🔍 Conteúdo de value:", value)

            # Só processa se houver mensagens
            if "messages" in value:
                mensagem = value["messages"][0]
                tipo = mensagem["type"]
                numero = mensagem["from"]

                # Verifica o tipo de mensagem
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
            else:
                print("⚠️ Nenhuma mensagem encontrada no payload.")

        except Exception as e:
            print("❌ Erro ao processar mensagem:", e)

        return jsonify({"status": "ok"}), 200

# 🚀 Inicia o servidor Flask na porta definida (Render usa variável PORT)
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    app.run(host="0.0.0.0", port=port)
