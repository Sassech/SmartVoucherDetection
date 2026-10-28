# llama-server + gemma-4-E2B-it-qat — Guía operativa

Servidor OCR multimodal local para SmartVoucherDetection. Corre el modelo
**gemma-4-E2B-it-qat** (GGUF) bajo **llama-server** de `llama.cpp`, exponiendo una API
compatible con OpenAI Chat Completions en `http://localhost:9931`.

> Esto es el **único componente fuera de Docker** del stack (en dev). Vive
> directamente en `llama.cpp/` porque la compilación de `llama.cpp` ya
> resolvió GPU offloading y dependencias del host.
>
> La API lo consume vía la variable de entorno `LLAMA_SERVER_URL`
> (por ejemplo `http://localhost:9931` desde el host).

---

## Setup (una sola vez)

Lo que ya está listo y commiteado bajo `llama.cpp/`:

| Carpeta / archivo | Contenido |
| --- | --- |
| `llama.cpp/llama-b11208/` | Binarios precompilados (build `b11208`, Vulkan) — incluye `llama-server`. |
| `llama.cpp/gemma-4-E2B-it-qat/gemma-4-E2B-it-qat-UD-Q4_K_XL.gguf` | Modelo principal (2.5 GB, cuantización Q4_K_XL). |
| `llama.cpp/gemma-4-E2B-it-qat/mmproj-BF16.gguf` | Proyector multimodal (942 MB, BF16) — necesario para imágenes. |
| `llama.cpp/gemma-4-E2B-it-qat/mtp-gemma-4-E2B-it.gguf` | Drafter MTP (57 MB) para decodificación especulativa. |
| `llama.cpp/gemma-4-E2B-it-qat.sh` | Wrapper que levanta el server con flags óptimos. |

Total en disco: ~3.5 GB.

> Si `llama.cpp/` se borra, hay que recompilar `llama.cpp` y re-bajar los
> `.gguf`. La carpeta está en `.gitignore` justamente porque pesa demasiado.

---

## Iniciar

```bash
./llama.cpp/gemma-4-E2B-it-qat.sh
```

El script lanza `llama-b11208/llama-server` con (resumen):

| Flag | Valor | Motivo |
| --- | --- | --- |
| `-m`  | `gemma-4-E2B-it-qat/gemma-4-E2B-it-qat-UD-Q4_K_XL.gguf` | Modelo principal (Q4_K_XL). |
| `-mm` | `gemma-4-E2B-it-qat/mmproj-BF16.gguf` | Proyector visual — sin esto no procesa imágenes. |
| `-a`  | `gemma-4-E2B-it-qat` | Alias del modelo expuesto en `/v1/models`. |
| `--model-draft` | `gemma-4-E2B-it-qat/mtp-gemma-4-E2B-it.gguf` | Drafter MTP para decodificación especulativa. |
| `--spec-type` | `draft-mtp` | Modo de decodificación especulativa. |
| `--spec-draft-n-max` | `4` | Tokens draft propuestos por paso. |
| `-c`  | `16384` | Contexto efectivo (KV barato por el SWA de Gemma 4). |
| `-ngl`| `99` | Offload completo a GPU (Vulkan sobre RTX 3050 Laptop 4GB). |
| `-b` / `-ub` | `2048` / `512` | Tamaños de batch físico y lógico. |
| `-ctk q8_0 -ctv q8_0` | KV cuantizado | Ahorra VRAM sin impacto medido en velocidad. |
| `--flash-attn` | `on` | Reduce memoria de KV cache. |
| `--temp 0 --top-p 1 --top-k 1 --repeat-penalty 1 --presence-penalty 0` | Decodificación greedy | OCR determinístico: mismo comprobante = mismo JSON. |
| `--reasoning off` | — | Desactiva el razonamiento del modelo. |
| `--cache-reuse` | `256` | Reutiliza el prefijo del prompt entre requests similares. |
| `--host 0.0.0.0 --port 9931` | — | Endpoint HTTP del server. |
| `-np 2` | — | Slots de paralelismo (ver nota abajo). |
| `-sm none` | — | Sin split entre GPUs. |

### Notas de rendimiento

- **Drafter MTP**: ~86-93 t/s vs ~70 t/s sin drafter (+25-31%); draft
  acceptance ~67-71%.
- **`-np 2`**: throughput combinado ~118 t/s, pero la latencia por comprobante
  sube de ~4.3s a ~7.3s (contención de GPU). Usar `-np 2` solo si el pipeline
  despacha comprobantes en paralelo (varios workers Celery); si es secuencial,
  `-np 1` da menor latencia por comprobante.
- **VRAM con `-np 1`**: 2714/4096 MiB.

El proceso queda en foreground; **Ctrl+C** dispara el `cleanup` que mata el
PID y libera el puerto 9931.

---

## Probar

### Health check

```bash
curl -s http://localhost:9931/health
# {"status":"ok"}
```

### Listar modelos cargados

```bash
curl -s http://localhost:9931/v1/models | jq
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
curl -s http://localhost:9931/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d "$(jq -n --arg uri "data:image/png;base64,${B64}" '{
    model: "gemma-4-E2B-it-qat",
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
  ss -tulpn | grep ':9931' | grep -oP 'pid=\K[0-9]+' | xargs -r kill -9
  ```

---

## Notas y limitaciones conocidas

- <!-- TODO: verificar --> **Diacríticos**: conviene verificar si el nuevo
  modelo sigue confundiendo caracteres acentuados (`MÉXICO` → `MÁXICO`).
  Para detección de duplicados (Fase 2) esto se mitiga con `pg_trgm` +
  Levenshtein, que tolera 1-2 chars de error.
- **Endpoint binding**: el server escucha en `0.0.0.0:9931`. No hay auth
  nativa: no expongas el puerto fuera del host. La API lo consume vía la
  variable de entorno `LLAMA_SERVER_URL` (p. ej. `http://localhost:9931`
  desde el host, `http://host.docker.internal:9931` desde un contenedor).
- **Para producción** (Fase 5): el modelo NO debe estar accesible
  públicamente. La API FastAPI lo proxea internamente y aplica auth/rate
  limit por encima.
- **GPU vs CPU**: `-ngl 99` hace offload completo a GPU vía Vulkan
  (confirmado en RTX 3050 Laptop 4GB: 36/36 capas cargadas). Si corrés en
  CPU pura bajá a `-ngl 0` y esperá tiempos significativamente mayores (>15s).
