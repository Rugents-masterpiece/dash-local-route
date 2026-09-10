FROM python:3.14-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends radeontop \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY app.py index.html services.json manage_services.py vasky_hero.png ./
COPY assets ./assets

ENV DASH_HOST=0.0.0.0
ENV DASH_PORT=8090
EXPOSE 8090

CMD ["python3", "app.py"]
