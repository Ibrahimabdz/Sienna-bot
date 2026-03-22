# Akinator Service

Ce service sort Akinator du bot principal.

## Variables

Service distant:

```env
AKINATOR_SERVICE_HOST=0.0.0.0
AKINATOR_SERVICE_PORT=8080
AKINATOR_SERVICE_TOKEN=un_token_long_et_prive
AKINATOR_BROWSER_PLATFORM=linux
AKINATOR_SERVICE_SESSION_TTL=1800
```

Bot principal:

```env
AKINATOR_SERVICE_URL=https://ton-service-akinator.example.com
AKINATOR_SERVICE_TOKEN=un_token_long_et_prive
AKINATOR_SERVICE_TIMEOUT=25
```

## Lancer le service

```bash
pip install -r requirements.txt
python akinator_service.py
```

## Healthcheck

```bash
curl http://127.0.0.1:8080/health
```

Si `AKINATOR_SERVICE_TOKEN` est défini, les routes `POST` exigent:

```http
Authorization: Bearer <token>
```

## Déploiement conseillé

- Héberge `akinator_service.py` sur une machine hors Railway.
- Garde le bot Discord principal sur Railway.
- Configure `AKINATOR_SERVICE_URL` et `AKINATOR_SERVICE_TOKEN` sur le bot principal.
- Vérifie `GET /health` avant de retester `/jeu akinator`.
