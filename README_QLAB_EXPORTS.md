# QBot -> QLab exports over HTTP

QBot exposes only generated QLab replay exports from:

```bash
/opt/qbot/app/qlab_exports/
```

It does not expose `/opt/qbot/app` or FIT source files.

## Token

Set a shared token in `/opt/qbot/app/.env`:

```env
QLAB_EXPORT_TOKEN=change-this-token
```

Every API request except `/health` must include:

```http
X-QLab-Token: change-this-token
```

## Export FIT

Default `fit-export` output goes to `qlab_exports`:

```bash
/opt/qbot/app/tools/fit-export/fit-export \
  --fit /opt/qbot/app/data/fit/garmin_22923840501.fit
```

This creates:

```bash
/opt/qbot/app/qlab_exports/22923840501.qbot_replay_log.json
/opt/qbot/app/qlab_exports/22923840501.qbot_replay_summary.json
```

## Start local API

```bash
/opt/qbot/app/qbot-qlab-server \
  --host 127.0.0.1 \
  --port 8899 \
  --exports /opt/qbot/app/qlab_exports
```

Endpoints:

- `GET /health`
- `GET /files`
- `GET /files/<filename>`
- `POST /export-fit`

## Start ngrok

Expose only the QLab export server:

```bash
ngrok http 8899
```

Use the generated ngrok HTTPS URL in QLab as `QBot URL`.

## curl examples

Health:

```bash
curl http://127.0.0.1:8899/health
```

List exports:

```bash
curl \
  -H "X-QLab-Token: change-this-token" \
  http://127.0.0.1:8899/files
```

Download an export:

```bash
curl \
  -H "X-QLab-Token: change-this-token" \
  http://127.0.0.1:8899/files/22923840501.qbot_replay_log.json
```

Create an export through the API:

```bash
curl \
  -X POST \
  -H "Content-Type: application/json" \
  -H "X-QLab-Token: change-this-token" \
  -d '{"fitPath":"/opt/qbot/app/data/fit/garmin_22923840501.fit"}' \
  http://127.0.0.1:8899/export-fit
```

QLab should call `GET <QBot URL>/files` with `X-QLab-Token`, show the returned files, then fetch the selected JSON from `/files/<filename>`. If the JSON contains `hudState`, QLab should load it as passthrough replay data.
