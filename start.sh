#!/bin/bash

echo "🚀 Ativando ambiente virtual..."
source .venv/bin/activate

echo "🧠 Iniciando servidor Flask (porta 5050)..."
# Executa o Flask com host 0.0.0.0 na porta 5050
python app.py &

# Aguarda 3 segundos para garantir que o Flask esteja no ar
sleep 3

echo "🌐 Iniciando ngrok na porta 5050..."
/Applications/ngrok.app/Contents/MacOS/ngrok http 5050
