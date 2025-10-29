# Folosim o imagine oficială Python
FROM python:3.11-slim

# Evităm mesajele interactive
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Setăm directorul de lucru în container
WORKDIR /app

# Copiem fișierul de dependențe și instalăm
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiem tot codul proiectului în container
COPY . .

# Expunem portul web (pentru Django)
EXPOSE 8000

# Comanda implicită (poate fi suprascrisă în docker-compose)
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
