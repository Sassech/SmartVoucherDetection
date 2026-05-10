# Git Flow — SmartVoucherDetection

Estrategia de ramas del proyecto. **Leer antes de hacer el primer push.**

## Ramas permanentes

| Rama | Proposito | Quien mergea |
|------|-----------|--------------|
| `main` | Codigo en produccion. Solo recibe merges desde `develop` o hotfixes. Cada merge a main = release candidata. | Solo via PR con CI verde |
| `develop` | Rama de integracion. Aqui se mergean todas las features completas. | PRs desde `feature/*` |

## Ramas temporales

| Patron | Proposito | Base | Destino |
|--------|-----------|------|---------|
| `feature/<nombre>` | Una feature nueva (ej: `feature/upload-endpoint`) | `develop` | `develop` |
| `fix/<nombre>` | Correccion de bug no-critico | `develop` | `develop` |
| `hotfix/<nombre>` | Correccion urgente en produccion | `main` | `main` Y `develop` |
| `chore/<nombre>` | Cambios de tooling, deps, configs (no codigo de negocio) | `develop` | `develop` |

## Convencion de commits

**Conventional Commits** obligatorio:

- `feat:` nueva funcionalidad
- `fix:` correccion de bug
- `chore:` mantenimiento (deps, configs, ignore, etc)
- `refactor:` cambio de codigo sin cambiar comportamiento
- `docs:` solo documentacion
- `test:` agregar o corregir tests
- `ci:` cambios en pipelines
- `perf:` mejoras de rendimiento

Ejemplo: `feat(api): add POST /upload-slip endpoint with OCR pipeline`

## Reglas de proteccion

`main` debe estar protegida en GitHub con:

1. Require PR antes de merge (no push directo)
2. Require CI verde (job `tests-api` y `lint`)
3. Require al menos 1 review aprobada
4. Require rama actualizada con base antes de merge
5. No allow force-push
6. No allow delete

`develop` mismas reglas pero **puede** permitir 0 reviews (uno solo trabajando en tesis).

## Tags y releases

Se taggea al cerrar cada fase del PROGRESO.md:

- `fase-0-completa`, `fase-1-completa`, ..., `fase-5-completa`
- Lanzamiento final: `v1.0.0`

Tags solo se crean en `main` despues del merge desde `develop`.

## Flujo tipico de una feature

```bash
git checkout develop && git pull
git checkout -b feature/scoring-engine
# ... trabajo + commits ...
git push -u origin feature/scoring-engine
# Abrir PR -> develop, esperar CI verde, mergear, borrar rama
```
