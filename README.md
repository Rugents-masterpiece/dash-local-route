# dash-local-route

Ľahký dashboard lokálnych webových služieb. Používa iba Python štandardnú knižnicu, bez externých balíkov.

## Spustenie

```bash
python3 app.py
```

Predvolene počúva na `0.0.0.0:8090`. Port a bind adresu možno zmeniť cez `DASH_PORT` a `DASH_HOST`.

Dashboard zobrazuje odkazy, HTTP health check, odozvu, CPU/RAM hostiteľa a procesy s najvyšším využitím.
