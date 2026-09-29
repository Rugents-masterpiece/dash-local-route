# dash-local-route

Ľahký dashboard lokálnych webových služieb. Používa iba Python štandardnú knižnicu, bez externých balíkov.

## Spustenie

```bash
python3 app.py
```

Predvolene počúva na `0.0.0.0:8090`. Port a bind adresu možno zmeniť cez `DASH_PORT` a `DASH_HOST`.

Dashboard zobrazuje odkazy, HTTP health check, odozvu, CPU hostiteľa, samostatné údaje oboch NVIDIA GPU (index, názov, PCI bus, využitie, VRAM a teplota), RAM a procesy s najvyšším využitím. AMD GPU už dashboard nesleduje. Ak ovládač alebo GPU metriku nemožno prečítať, príslušná karta zobrazí `N/A`.

## Externý register služieb

Zoznam je v `services.json`, nie v HTML/JavaScripte. Dashboard ho načíta pri každom `/api/status`, takže zmena sa prejaví bez rebuild-u kontajnera. Upravuj ho cez atomický nástroj:

```bash
python3 manage_services.py list
python3 manage_services.py add "Moja služba" http://127.0.0.1:1234/ --description "..." --source /cesta/projektu --restart-command "..."
python3 manage_services.py remove "Moja služba"
python3 manage_services.py maintenance "Moja služba" on
python3 manage_services.py maintenance "Moja služba" off
```

`managed: false` alebo `maintenance: true` znamená, že automatická úloha službu iba skontroluje a nespustí opravu/reštart. Pri ručnej práci teda zapni údržbu; odstránenie z registra je voliteľné. `restart_command` je jediný príkaz, ktorý smie automatická úloha použiť na reštart konkrétnej služby; bez neho iba diagnostikuje a nahlási príčinu.

Dashboard zobrazuje aj stav Hermes watchdogu, čas posledného behu, počet povolených reštartov a posledný krátky report. Stav je čítaný z cron výstupu a z `/home/rugent/.hermes/state/service-watchdog.json`; prompt a citlivé údaje sa do dashboardu neposielajú.

## Chránené služby

Orbit a OpenViking Studio sa otvárajú cez lokálnu autentifikovanú proxy:

- `/proxy/orbit/`
- `/proxy/openviking/studio/`

Na karte služby sa pre Orbit zadáva upstream `auth_token`. Pre OpenViking sa zadáva heslo z `openviking-user.env`; backend ho pri login requeste namapuje na platný upstream kľúč z `hermes.env`. Skutočný upstream kľúč sa posiela iba v HTTP hlavičkách, nie v URL ani HTML, a dashboard ho drží iba v pamäti serverovej relácie s `HttpOnly` cookie. Prihlásenie je platné iba pre vybranú službu. OpenViking heslo sa číta pri každom login requeste, takže po jeho zmene netreba reštart dashboardu.

Proxy nie je náhrada za HTTPS ani plnohodnotný používateľský systém. Používaj ho iba v dôveryhodnej LAN; pre internetové vystavenie treba TLS, pevný dashboard login a CSRF ochranu.
