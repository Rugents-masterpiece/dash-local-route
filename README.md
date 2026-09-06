# dash-local-route

Ľahký dashboard lokálnych webových služieb. Používa iba Python štandardnú knižnicu, bez externých balíkov.

## Spustenie

```bash
python3 app.py
```

Predvolene počúva na `0.0.0.0:8090`. Port a bind adresu možno zmeniť cez `DASH_PORT` a `DASH_HOST`.

Dashboard zobrazuje odkazy, HTTP health check, odozvu, CPU hostiteľa, samostatné využitie NVIDIA a AMD GPU, RAM a procesy s najvyšším využitím. Ak ovládač alebo GPU metriku nemožno prečítať, príslušná karta zobrazí `N/A`.
