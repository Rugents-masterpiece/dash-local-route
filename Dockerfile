FROM python:3.14-slim

WORKDIR /app
COPY app.py stt_identity.py index.html services.json manage_services.py vasky_hero.png ./
COPY assets ./assets

ENV DASH_HOST=0.0.0.0
ENV DASH_PORT=8090
EXPOSE 8090

CMD ["python3", "app.py"]
