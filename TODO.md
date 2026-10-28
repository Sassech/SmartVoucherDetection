# TODO — Pendientes del repo

> Última actualización: 2026-10-26
> Modelo OCR actual: `gemma-4-E2B-it-qat` servido vía `llama.cpp/` (drafter MTP, offload Vulkan RTX 3050 4GB, puerto 9931).

- [ ] **Actualizar 32 referencias a GLM-OCR en 6 docs** (quedaron desactualizadas tras el switch a gemma-4-E2B-it-qat):
  - `README.md`
  - `docs/ARCHITECTURE.md`
  - `docs/DEPLOYMENT.md`
  - `docs/llama-server.md` — ⚠️ runbook operativo: apunta a `llama.cpp/GLM-OCR/*.gguf` que ya no existen; reescribir con la config nueva (gemma-4-E2B-it-qat, offload Vulkan, drafter MTP, `-np 2`, `--cache-reuse 256`, puerto 9931)
  - `cosas/plan_desarrollo.md`
  - `cosas/RUNBOOK.md`
- [ ] `infra/docker-compose.prod.yml:6` — comentario viejo aún menciona gemma (vestigio; revisar coherencia)
- [x] `docs/dataset-evaluation.md` — llenado completo 2026-10-26: SROIE PASS (F1 monto 0.8225, fecha 0.9356), bancario v2 (3 capas + matriz 3×3), guía de reproducción a mano §4.4
- [ ] **Leer el guion de defensa completo de punta a punta antes de la defensa** (verificar que los slides 13/19/21 omisibles sigan siendo los correctos tras las ediciones del 2026-10-26)

## Hecho (2026-10-26)

- [x] Migración de referencias: guion de defensa, `api/config.py` (alias `gemma-4-E2B-it-qat`), `api/services/ocr_service.py`, `api/schemas/health.py`, `api/services/parser_service.py` — 18 tests unitarios pasan
- [x] Métricas reales en guion: capa 1 P=1.0/R=0.4286, capa 2 F1=1.0, capa 3 P=1.0/R=0.9714/F1=0.9855; RNF-01=5s corregido
