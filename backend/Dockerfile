FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Exposition du port de l'application
EXPOSE 8000

# Commande par défaut pour démarrer l'application
CMD ["python", "start.py"]
