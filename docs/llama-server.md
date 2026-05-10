# llama-server + GLM-OCR — Guía operativa

Servidor OCR multimodal local para SmartVoucherDetection. Corre el modelo
**GLM-OCR** (GGUF) bajo **llama-server** de `llama.cpp`, exponiendo una API
compatible con OpenAI Chat Completions en `http://localhost:8080`.

> Esto es el **único componente fuera de Docker** del stack (en dev). Vive
> directamente en `llama.cpp/` porque la compilación de `llama.cpp` ya
> resolvió GPU offloading y dependencias del host.

---

## Setup (una sola vez)

Lo que ya está listo y commiteado bajo `llama.cpp/`:

| Carpeta / archivo | Contenido |
| --- | --- |
| `llama.cpp/llama-b9012/` | Binarios precompilados (release `b9012`) — incluye `llama-server`. |
| `llama.cpp/GLM-OCR/GLM-OCR-f16.gguf` | Modelo principal (~1.78 GB, 891M params, ctx train 131072). |
| `llama.cpp/GLM-OCR/mmproj-GLM-OCR-Q8_0.gguf` | Proyector multimodal (necesario para imágenes). |
| `llama.cpp/GLM-OCR.sh` | Wrapper que levanta el server con flags óptimos. |

> Si `llama.cpp/` se borra, hay que recompilar `llama.cpp` y re-bajar los
> `.gguf`. La carpeta está en `.gitignore` justamente porque pesa demasiado.

---

## Iniciar

```bash
./llama.cpp/GLM-OCR.sh
```

El script lanza `llama-server` con (resumen):

| Flag | Valor | Motivo |
| --- | --- | --- |
| `-m`  | `GLM-OCR/GLM-OCR-f16.gguf` | Modelo principal. |
| `-mm` | `GLM-OCR/mmproj-GLM-OCR-Q8_0.gguf` | Proyector visual — sin esto no procesa imágenes. |
| `-a`  | `GLM-OCR` | Alias del modelo expuesto en `/v1/models`. |
| `-c`  | `16384` | Context efectivo. |
| `-ngl`| `14` | Capas en GPU. Ajustar según VRAM disponible. |
| `--flash-attn` | `on` | Reduce memoria de KV cache. |
| `-ctk q8_0 -ctv q8_0` | KV cuantizado | Más imágenes en memoria sin saturar. |
| `--temp 0 --top-p 1 --top-k 1` | Determinístico | OCR no debe alucinar. |
| `--port` | `8080` | Endpoint HTTP. |

El proceso queda en foreground; **Ctrl+C** dispara el `cleanup` que mata el
PID y libera el puerto 8080.

---

## Probar

### Health check

```bash
curl -s http://localhost:8080/health
# {"status":"ok"}
```

### Listar modelos cargados

```bash
curl -s http://localhost:8080/v1/models | jq
```

### Smoke test OCR completo

```bash
./infra/scripts/smoke_test_ocr.sh
# [INFO] Enviando .../sample_comprobante.png (image/png) a ...
# [INFO] Tokens generados: 136 | tiempo: 3.73s
# OK — texto extraído: BBVA ...
```

El script:

1. Genera/reutiliza una imagen sintética en `infra/scripts/fixtures/`.
2. La codifica como `data:image/png;base64,...`.
3. Hace `POST /v1/chat/completions` con prompt OCR.
4. Mide tiempo y valida `< 5s` (warning si supera).

Para regenerar la imagen sintética:

```bash
uv run --project api python infra/scripts/generate_sample.py
```

### Llamada manual con curl

```bash
B64=$(base64 -w0 mi_comprobante.png)
curl -s http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d "$(jq -n --arg uri "data:image/png;base64,${B64}" '{
    model: "GLM-OCR",
    temperature: 0,
    messages: [{
      role: "user",
      content: [
        {type: "text", text: "Extrae el texto del comprobante."},
        {type: "image_url", image_url: {url: $uri}}
      ]
    }]
  }')" | jq -r '.choices[0].message.content'
```

---

## Apagar

- **Foreground**: `Ctrl+C` en la terminal del script.
- **Si quedó zombi**:

  ```bash
  pkill -9 -f llama-server
  # o por puerto
  ss -tulpn | grep ':8080' | grep -oP 'pid=\K[0-9]+' | xargs -r kill -9
  ```

---

## Notas y limitaciones conocidas

- **Diacríticos**: el modelo a veces confunde caracteres acentuados
  (`MÉXICO` → `MÁXICO`). Para detección de duplicados (Fase 2) esto se
  mitiga con `pg_trgm` + Levenshtein, que tolera 1-2 chars de error.
- **Endpoint binding**: el server escucha en `127.0.0.1:8080` (loopback). Si
  necesitás acceso desde otro contenedor, hay que pasar `--host 0.0.0.0` en
  el script y exponerlo con cuidado (no hay auth nativa).
- **Para producción** (Fase 5): el modelo NO debe estar accesible
  públicamente. La API FastAPI lo proxea internamente y aplica auth/rate
  limit por encima.
- **GPU vs CPU**: `-ngl 14` espera GPU compatible. Si corrés en CPU pura
  bajá a `-ngl 0` y esperá tiempos significativamente mayores (>15s).
