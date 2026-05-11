# Exploración: Plugin WordPress Gratuito — Fase 3

**Fecha:** 2026-05-10  
**Generado por:** sdd-explore  
**Objetivo:** Análisis consolidado de Fase 3 para que el orquestador proponga un plan de implementación concreto.

---

## 1. Las 14 tareas de PROGRESO.md Fase 3 — evaluación de scope

### Listado original (PROGRESO.md §326–344)

| # | Tarea | ¿Bien scoped? | Observación |
|---|-------|--------------|-------------|
| 3.1 | Estructura `plugin-wp/comprobantes-ocr/` | ✅ | Directa: entry point + readme.txt + includes/ |
| 3.2 | Clase `API_Client` con `wp_remote_post()` | ✅ | Única clase con responsabilidad clara |
| 3.3 | Página de configuración wp-admin | ✅ | Settings API estándar |
| 3.4 | Shortcode `[comprobante_upload]` con drag-and-drop | ⚠️ | Mezcla PHP (registro) + JS (UX). Debería dividirse: 3.4a = PHP class-shortcode.php, 3.4b = JS upload-handler.js |
| 3.5 | Bloque Gutenberg equivalente al shortcode | ⚠️ | Requiere build step (wp-scripts/Webpack). Es una tarea no-trivial separada del shortcode. |
| 3.6 | Semáforo visual (verde/amarillo/rojo) vía JS | ✅ | result-display.js — renderizado puro JS, bien aislado |
| 3.7 | Widget historial últimos 20 en wp-admin | ✅ | history-widget.php — consulta a API `/history` |
| 3.8 | Hook WooCommerce `woocommerce_order_status_completed` | ✅ | Un único hook, bien delimitado |
| 3.9 | Seguridad: nonce, sanitización, capability checks | ⚠️ | No es una tarea separada — la seguridad es TRANSVERSAL a 3.3, 3.4, 3.7, 3.8. Debería ser un checklist en cada tarea, no una tarea aparte que se "hace al final". |
| 3.10 | i18n: archivos .pot, traducciones es_MX y en_US | ✅ | load_plugin_textdomain() + WP-CLI makepot |
| 3.11 | Assets WP.org: banner, ícono, screenshots | ✅ | Activos de directorio, no código |
| 3.12 | `readme.txt` formato oficial WP.org | ✅ | Formato SVN-style requerido |
| 3.13 | Pasar Plugin Check sin errores críticos | ✅ | Criterio de aceptación ejecutable |
| 3.14 | Workflow GitHub Actions para generar ZIP en tags | ✅ | Job `build-plugin` ya mencionado en plan (Fase 5.7) — se puede anticipar aquí |

**Veredicto:** 14 tareas son razonables en cantidad pero requieren 3 refinamientos:
1. **3.4 dividir** en 3.4a (PHP) y 3.4b (JS/AJAX) — el drag-and-drop implica wp_enqueue_scripts, admin-ajax.php handler y fetch JS, nada trivial.
2. **3.5 requiere subtarea explícita de build**: `npm init @wordpress/scripts` — sin esto el bloque no puede existir.
3. **3.9 seguridad** debe estar embebida en 3.3/3.4/3.7/3.8, no ser tarea final. Mantenerla como tarea de *revisión* y *Plugin Check* es válido, pero aclarar que no es "implementar seguridad al final".

---

## 2. Especificación Fase 3 según plan_desarrollo.md

### 2.1 Estructura del plugin (§3.1)

```
comprobantes-ocr/
├── comprobantes-ocr.php        # Entry point, hooks WP, GPL header
├── readme.txt                  # WP.org format (SVN)
├── includes/
│   ├── class-api-client.php    # wp_remote_post() → FastAPI
│   ├── class-shortcode.php     # [comprobante_upload]
│   ├── class-gutenberg.php     # Block registration + enqueue
│   ├── class-settings.php      # Settings API (URL + API key + timeout)
│   └── class-woo-hook.php      # WooCommerce integration
├── admin/
│   ├── settings-page.php       # Render de la página de ajustes
│   └── history-widget.php      # Widget con últimos 20 comprobantes
├── public/
│   ├── js/upload-handler.js    # AJAX + fetch → admin-ajax.php
│   ├── js/result-display.js    # Semáforo visual
│   └── css/styles.css
├── block/                      # ← No en el plan, pero NECESARIO para Gutenberg
│   ├── block.json
│   ├── src/edit.js
│   ├── src/save.js
│   └── build/                  # Generado por wp-scripts
└── languages/
    ├── comprobantes-ocr.pot
    ├── comprobantes-ocr-es_MX.po/.mo
    └── comprobantes-ocr-en_US.po/.mo
```

> **Gap en el plan:** el directorio `block/` y el build step con `@wordpress/scripts` no están listados. Sin esto, el bloque Gutenberg no puede existir. Necesita `package.json` en `plugin-wp/comprobantes-ocr/` con `"@wordpress/scripts": "^30.x"`.

### 2.2 Funcionalidades por área (§3.2)

| Área | Implementación concreta |
|------|------------------------|
| Settings wp-admin | `Settings API` → `register_setting()`, `add_settings_section()`, `add_settings_field()`. Menú en `options-general.php`. Botón "Probar conexión" llama `wp_remote_get('/health')` vía AJAX. Campos: `comprobantes_api_url`, `comprobantes_api_key`, `comprobantes_timeout` (default 30s). |
| Shortcode | `add_shortcode('comprobante_upload', [$this, 'render'])`. HTML: form con `enctype="multipart/form-data"`, drag-and-drop CSS, JS fetch a `admin-ajax.php`. |
| Bloque Gutenberg | `register_block_type()` usando `block.json`. React/JSX en `src/edit.js` con `ServerSideRender` o compilado como bloque dinámico. Build: `wp-scripts build`. |
| Semáforo | JS puro: `{ estado: 'valido'|'sospechoso'|'duplicado', score }` → DOM manipulation con clases CSS. Botón "revisar" en sospechoso. |
| Historial wp-admin | Menú secundario o meta box. Llamada a `GET /history?limit=20` vía `wp_remote_get()`. Renderizado PHP con tabla HTML y `esc_html()`. |
| WooCommerce hook | `add_action('woocommerce_order_status_completed', [$this, 'validate_slip'])`. Busca adjunto del pedido, llama `POST /upload-slip/async`, guarda `task_id` en order meta. |
| Seguridad | `wp_create_nonce('comprobante_upload')` en formulario, `check_ajax_referer()` en handler AJAX, `current_user_can('manage_options')` en settings, `sanitize_text_field()` en todo input, `esc_html()/esc_attr()/esc_url()` en todo output. |
| i18n | `load_plugin_textdomain('comprobantes-ocr', false, basename(dirname(__FILE__)).'/languages/')` en `plugins_loaded`. `__()` y `_e()` en todas las strings. |

### 2.3 Flujo de comunicación Plugin ↔ API (§3.3)

```
[Browser]
  └─ FormData (file + nonce) → POST admin-ajax.php?action=comprobante_upload
      └─ [PHP AJAX handler in class-shortcode.php]
          ├─ check_ajax_referer('comprobante_upload')
          ├─ current_user_can('upload_files') o similar
          └─ API_Client::upload($file_data)
              └─ wp_remote_post(API_URL . '/upload-slip', [
                    'headers' => ['X-API-Key' => get_option('comprobantes_api_key')],
                    'body'    => [...],
                    'timeout' => get_option('comprobantes_timeout', 30),
                  ])
                  └─ JSON response → wp_send_json_success/error()
```

> **Decisión de auth confirmada:** El plugin usa `X-API-Key: {api_key}` header. La API **actualmente** NO valida este header (SYSTEM_USER_ID hardcoded, auth real en Fase 4). Para Fase 3, la API necesita un middleware mínimo de API key que valide el header contra `token_api_hash` en la tabla `usuarios`. Ver §4.1 — riesgo de acoplamiento.

### 2.4 Preparación WP.org (§3.4)

- `readme.txt` requiere: `=== Plugin Name ===`, `Requires at least: 6.0`, `Tested up to: 6.5`, `Stable tag:`, `License: GPL v2 or later`, `== Description ==`, `== Installation ==`, `== Changelog ==`
- `Plugin Check` (plugin oficial de WordPress) valida: namespace/prefix, escape de output, sanitización de input, ausencia de errores PHP, capacidades, i18n
- Assets directorio WP.org: `assets/banner-1544x500.png`, `assets/icon-256x256.png`, `assets/screenshot-1.png`
- GitHub Actions: job `build-plugin` en `on: push: tags: ['v*']` — `zip -r comprobantes-ocr.zip comprobantes-ocr/ --exclude "*.git*" "node_modules/*" "src/*"` → adjuntar al Release

---

## 3. Estructura correcta del directorio para WP.org

```
plugin-wp/
└── comprobantes-ocr/           # ← Slug del plugin (debe coincidir con el textdomain)
    ├── comprobantes-ocr.php    # Header GPL obligatorio
    ├── readme.txt
    ├── uninstall.php           # Limpieza de options en desinstalación
    ├── includes/
    │   ├── class-api-client.php
    │   ├── class-shortcode.php
    │   ├── class-gutenberg.php
    │   ├── class-settings.php
    │   └── class-woo-hook.php
    ├── admin/
    │   ├── settings-page.php
    │   └── history-widget.php
    ├── public/
    │   ├── js/
    │   │   ├── upload-handler.js
    │   │   └── result-display.js
    │   └── css/
    │       └── styles.css
    ├── block/
    │   ├── package.json        # @wordpress/scripts
    │   ├── block.json          # Metadata del bloque
    │   ├── src/
    │   │   ├── edit.js
    │   │   ├── save.js
    │   │   └── index.js
    │   └── build/              # Generado — incluir en .gitignore parcial (solo src)
    ├── languages/
    │   ├── comprobantes-ocr.pot
    │   ├── comprobantes-ocr-es_MX.po
    │   ├── comprobantes-ocr-es_MX.mo
    │   ├── comprobantes-ocr-en_US.po
    │   └── comprobantes-ocr-en_US.mo
    └── assets/                 # WP.org directory assets (NO se incluyen en el ZIP del plugin)
        ├── banner-1544x500.png
        ├── icon-256x256.png
        └── screenshot-1.png
```

**Convenciones WP.org críticas:**
- Prefijo en todas las funciones/clases/constantes: `comprobantes_ocr_` / `Comprobantes_OCR_` / `COMPROBANTES_OCR_`
- Nunca `define()` sin prefix, nunca variables globales sin prefix
- `uninstall.php` es OBLIGATORIO para borrar options al desinstalar (no solo desactivar)
- El slug del directorio (`comprobantes-ocr`) debe coincidir con `Text Domain` en el header y con el parámetro de `load_plugin_textdomain()`

---

## 4. API Client — integración con el backend FastAPI

### 4.1 El problema de auth en Fase 3 vs. Fase 4

**Estado actual (Fase 2 completada):**
- `SYSTEM_USER_ID` hardcoded en `routers/upload.py` línea ~36-38
- El modelo `Usuario.token_api_hash` EXISTE (campo `String(255) nullable`) pero NO hay middleware que lo valide
- No hay endpoint de generación de API keys
- CORS está abierto (`allow_origins=["*"]`)

**Lo que Fase 3 necesita:**
- El plugin envía `X-API-Key: <plain_token>` en cada request
- La API debe validar: extraer `X-API-Key`, buscar un `Usuario` con `bcrypt.checkpw(token, token_api_hash)`, inyectar `id_usuario` en el request
- Sin esto, cualquier persona puede llamar a la API sin autenticación

**Opciones:**

| Opción | Descripción | Pros | Contras | Complejidad |
|--------|-------------|------|---------|-------------|
| A — Auth mínima en Fase 3 | Middleware FastAPI que valida `X-API-Key` contra `token_api_hash` | Seguro desde día 1, no deuda | Pequeño scope adicional a la API | Baja |
| B — Auth falsa (hardcodear key) | La API acepta cualquier valor en `X-API-Key` o un valor hardcoded en `.env` | Zero effort | Inseguro, deuda explícita | Mínima |
| C — Diferir auth a Fase 4 | El plugin funciona sin header de auth; la API sigue con SYSTEM_USER_ID | Plugin simple | Producto inseguro en prod | Cero |

> **Recomendación:** Opción A, pero con scope mínimo: un endpoint `POST /auth/api-key` (genera key, la muestra una vez) + un dependency FastAPI `require_api_key` que reemplaza el `SYSTEM_USER_ID` hardcoded. Esto es ~80 LOC adicionales en la API y desbloquea un producto seguro desde el lanzamiento. Si el usuario prefiere diferir, la Opción C es válida con una deuda técnica explícita documentada.

### 4.2 Diseño de `class-api-client.php`

```php
class Comprobantes_OCR_API_Client {
    private string $base_url;
    private string $api_key;
    private int $timeout;

    public function __construct() {
        $this->base_url = rtrim(get_option('comprobantes_api_url', ''), '/');
        $this->api_key  = get_option('comprobantes_api_key', '');
        $this->timeout  = (int) get_option('comprobantes_timeout', 30);
    }

    public function upload_slip(array $file): array|\WP_Error {
        // wp_remote_post con multipart/form-data
        // Header: X-API-Key
        // Timeout configurable
        // Manejo de WP_Error (network) y HTTP 4xx/5xx
    }

    public function health_check(): bool|\WP_Error {
        // wp_remote_get('/health')
    }

    public function get_history(int $limit = 20): array|\WP_Error {
        // wp_remote_get('/history?limit=' . $limit)
    }

    private function make_request(string $method, string $endpoint, array $args = []): array|\WP_Error {
        // Método privado unificado: base_url + endpoint, headers comunes, timeout
        // wp_remote_request($url, $args)
        // Retorna body decodificado o WP_Error
    }
}
```

**Patrón de error handling:**
- Errores de red → `WP_Error` con código `api_network_error`
- HTTP 4xx → `WP_Error` con código `api_client_error` + mensaje del JSON de respuesta
- HTTP 5xx → `WP_Error` con código `api_server_error`
- JSON inválido → `WP_Error` con código `api_invalid_response`
- NUNCA `die()` o `exit()` en un plugin

---

## 5. Scope del hook WooCommerce

**Un solo hook, bien delimitado:**

```php
// En class-woo-hook.php
add_action('woocommerce_order_status_completed', [$this, 'on_order_completed']);

public function on_order_completed(int $order_id): void {
    $order = wc_get_order($order_id);
    // 1. Buscar adjunto tipo comprobante en el pedido (order meta o nota)
    // 2. Si existe: llamar API_Client::upload_slip() modo ASYNC
    // 3. Guardar task_id en order meta: update_post_meta($order_id, '_comprobante_task_id', $task_id)
    // 4. Agregar nota al pedido: $order->add_order_note('Comprobante enviado a validación...')
    // 5. Si la API retorna duplicado: $order->update_status('on-hold', 'Comprobante duplicado detectado')
    // 6. Logging vía error_log() (no die/exit)
}
```

**Scope limitado (NO incluye):**
- Polling del estado de la tarea async (requeriría un cron job o webhook de vuelta)
- Bloqueo del pedido antes de completarse (requeriría `woocommerce_checkout_process`)
- UI en el panel de WooCommerce (Fase 4 o futura extensión)
- Validación de métodos de pago específicos

**Decisión de diseño:** La integración usa modo **async** (`POST /upload-slip/async`) porque WooCommerce no debe esperar la respuesta del OCR. El `task_id` se guarda en order meta para futura consulta manual o webhook de Fase 4.

---

## 6. Scope i18n

### 6.1 Lo que implica realmente

- `load_plugin_textdomain('comprobantes-ocr', false, dirname(plugin_basename(__FILE__)) . '/languages/')` en hook `plugins_loaded`
- Todas las strings PHP con `__('...', 'comprobantes-ocr')` o `_e('...', 'comprobantes-ocr')`
- Strings JavaScript con `wp_localize_script()` para pasar translations al JS (WordPress no tiene i18n nativa para JS en plugins simples — el bloque Gutenberg sí usa `@wordpress/i18n`)
- Generar `.pot`: `wp i18n make-pot plugin-wp/comprobantes-ocr/ plugin-wp/comprobantes-ocr/languages/comprobantes-ocr.pot`
- Compilar `.po` → `.mo`: `wp i18n make-mo languages/comprobantes-ocr-es_MX.po`

### 6.2 ¿Necesita flujo .pot complejo?

**No para Fase 3.** El flujo es simple:
1. Escribir código con `__()` correctamente
2. Una vez al finalizar: `wp i18n make-pot` (WP-CLI) para extraer strings
3. Crear `es_MX.po` manualmente (son pocas strings — shortcode, settings, mensajes)
4. Compilar `.mo` con `wp i18n make-mo`

No se necesita GlotPress, Transifex ni Poedit — WP-CLI es suficiente. El `.pot` se incluye en el ZIP para que la comunidad pueda traducir en el futuro.

**Strings estimadas:** ~30-40 strings (labels de settings, mensajes del semáforo, botones, mensajes de error). Manejable en una sesión.

---

## 7. Riesgos identificados

### 7.1 Riesgo alto: Autenticación API en Fase 3

- **Problema:** La API actualmente no valida `X-API-Key`. Sin autenticación real, el plugin produce un producto inseguro.
- **Mitigación:** Implementar middleware mínimo de API key en FastAPI como parte de Fase 3 (scope adicional ~80 LOC en Python, no en PHP).
- **Si se difiere:** Documentar explícitamente en el código que la API acepta cualquier request y que Fase 4 agrega JWT.

### 7.2 Riesgo medio: Bloque Gutenberg — build step obligatorio

- **Problema:** El bloque requiere Node.js + `@wordpress/scripts` para compilar. Esto es una dependencia de toolchain que no existe en el proyecto.
- **Mitigación:** Añadir `package.json` dentro de `plugin-wp/comprobantes-ocr/block/` con build script. El build resultante se versiona en Git (`build/` no se ignora). El workflow de CI necesita `npm install && npm run build` antes de generar el ZIP.
- **Alternativa:** Usar `ServerSideRender` (deprecated) o escribir el bloque sin JSX (puro `wp.element.createElement` en JS vanilla). Esto evita el build step pero produce código menos mantenible.

### 7.3 Riesgo medio: Plugin Check — requisitos estrictos WP.org

WP.org Plugin Check (2024+) falla con:
- Output sin escapar (cualquier `echo $variable` sin `esc_html()`)
- `$_POST/$_GET` sin `sanitize_*()`
- Capacidades no verificadas antes de acciones admin
- Falta de `check_ajax_referer()` en handlers AJAX
- Uso directo de `$wpdb->query()` con datos no preparados
- `define()` sin prefix

**Todos estos se previenen si se sigue el checklist de seguridad desde el inicio.**

### 7.4 Riesgo bajo: PHP version constraint

WP.org requiere `Requires PHP: 7.4+` mínimo para subir el plugin. WordPress 6.5 recomienda PHP 8.1+. Las features de PHP 8.x (named arguments, match expressions, union types en firmas) son seguras de usar si declaramos `Requires PHP: 8.0`.

- **Recomendación:** declarar `Requires PHP: 8.0` en el header — está alineado con WP 6.5+ y evita workarounds de PHP 7.x.
- **Riesgo real:** mínimo, ya que el entorno de desarrollo usa PHP 8.x.

### 7.5 Riesgo bajo: WooCommerce como dependencia opcional

WooCommerce NO debe ser requerido. Si WooCommerce no está activo, la clase `Comprobantes_OCR_Woo_Hook` simplemente no se instancia.

```php
// En comprobantes-ocr.php (entry point)
if (class_exists('WooCommerce')) {
    require_once plugin_dir_path(__FILE__) . 'includes/class-woo-hook.php';
    new Comprobantes_OCR_Woo_Hook();
}
```

### 7.6 Riesgo bajo: upload multipart vía wp_remote_post

`wp_remote_post()` con `multipart/form-data` y archivos binarios requiere formato específico en el body. WordPress usa `WP_Http` internamente — para archivos binarios hay que usar `cURL_boundary` manual o la forma de array que WP_Http procesa. Es documentable pero no trivial.

**Alternativa investigada:** Usar `WP_HTTP_Requests_Response` directamente o encodear el archivo como base64 en el body JSON. Base64 evita el multipart pero aumenta el tamaño del payload ~33%. Para comprobantes de ≤10MB, aceptable.

---

## 8. Estimaciones de LOC

| Área | Archivos principales | LOC estimado |
|------|---------------------|-------------|
| Entry point + scaffolding (3.1) | `comprobantes-ocr.php`, `uninstall.php` | ~100 |
| API Client PHP (3.2) | `class-api-client.php` | ~150 |
| Settings wp-admin (3.3) | `class-settings.php`, `settings-page.php` | ~200 |
| Shortcode PHP + AJAX handler (3.4a) | `class-shortcode.php` | ~150 |
| JS upload + semáforo (3.4b + 3.6) | `upload-handler.js`, `result-display.js`, `styles.css` | ~250 |
| Bloque Gutenberg (3.5) | `block.json`, `src/*.js`, build config | ~200 |
| Historial widget (3.7) | `history-widget.php` | ~100 |
| WooCommerce hook (3.8) | `class-woo-hook.php` | ~80 |
| i18n (3.10) | `*.po`, `*.pot`, strings en todo el código | ~30 strings |
| WP.org assets (3.11) | `readme.txt`, imágenes | ~80 LOC (readme) |
| GitHub Actions ZIP (3.14) | `.github/workflows/build-plugin.yml` | ~40 |
| **API auth mínima (extra)** | FastAPI middleware + endpoint `/auth/api-key` | ~80 (Python) |
| **TOTAL** | ~23 archivos PHP/JS + config | **~1,430 LOC (plugin) + 80 LOC (API)** |

> **Chained PRs:** Con ~1,430 LOC de código nuevo (PHP/JS) en un componente hasta ahora vacío, **sí es candidato a chained PRs**. La división natural sería:
> - **PR-A:** Scaffolding + API Client + Settings (3.1 + 3.2 + 3.3) — ~450 LOC
> - **PR-B:** Shortcode + JS + Semáforo (3.4 + 3.6) — ~400 LOC
> - **PR-C:** Gutenberg block (3.5) — ~200 LOC (independiente, tiene su propio toolchain)
> - **PR-D:** WooCommerce + i18n + WP.org + CI (3.8 + 3.10 + 3.11 + 3.12 + 3.13 + 3.14) — ~380 LOC

---

## 9. Archivos afectados

| Archivo | Cambio | Lenguaje |
|---------|--------|----------|
| `plugin-wp/comprobantes-ocr/comprobantes-ocr.php` | CREAR — entry point | PHP |
| `plugin-wp/comprobantes-ocr/uninstall.php` | CREAR | PHP |
| `plugin-wp/comprobantes-ocr/readme.txt` | CREAR | Text |
| `plugin-wp/comprobantes-ocr/includes/class-api-client.php` | CREAR | PHP |
| `plugin-wp/comprobantes-ocr/includes/class-shortcode.php` | CREAR | PHP |
| `plugin-wp/comprobantes-ocr/includes/class-gutenberg.php` | CREAR | PHP |
| `plugin-wp/comprobantes-ocr/includes/class-settings.php` | CREAR | PHP |
| `plugin-wp/comprobantes-ocr/includes/class-woo-hook.php` | CREAR | PHP |
| `plugin-wp/comprobantes-ocr/admin/settings-page.php` | CREAR | PHP |
| `plugin-wp/comprobantes-ocr/admin/history-widget.php` | CREAR | PHP |
| `plugin-wp/comprobantes-ocr/public/js/upload-handler.js` | CREAR | JS |
| `plugin-wp/comprobantes-ocr/public/js/result-display.js` | CREAR | JS |
| `plugin-wp/comprobantes-ocr/public/css/styles.css` | CREAR | CSS |
| `plugin-wp/comprobantes-ocr/block/package.json` | CREAR | JSON |
| `plugin-wp/comprobantes-ocr/block/block.json` | CREAR | JSON |
| `plugin-wp/comprobantes-ocr/block/src/*.js` | CREAR | JSX |
| `plugin-wp/comprobantes-ocr/languages/*.pot/.po/.mo` | CREAR | i18n |
| `plugin-wp/comprobantes-ocr/assets/*.png` | CREAR | Image |
| `.github/workflows/build-plugin.yml` | CREAR | YAML |
| `api/routers/auth.py` | CREAR (opcional Fase 3) — endpoint API key | Python |
| `api/dependencies/auth.py` | CREAR (opcional) — middleware API key | Python |
| `openspec/config.yaml` | MODIFICAR — agregar testing PHP config | YAML |

---

## 10. Decisiones previas que el orquestador debe plantear al usuario

### Decisión 1 (BLOQUEANTE): ¿Implementar auth de API key en Fase 3?

- **Opción A (Recomendada):** Agregar middleware FastAPI mínimo (`X-API-Key` → bcrypt check) + endpoint `POST /auth/generate-key` que genera y devuelve la key una vez. ~80 LOC en Python. Seguro desde el lanzamiento.
- **Opción B:** Diferir a Fase 4. El plugin funciona pero cualquiera que conozca la URL de la API puede usarla. Documentar como deuda conocida.

### Decisión 2 (IMPORTANTE): ¿Bloque Gutenberg en Fase 3 o diferir?

- **Opción A (Plan original):** Implementar en Fase 3. Requiere Node.js + `@wordpress/scripts` build step. Añade complejidad al CI workflow.
- **Opción B:** Diferir el bloque a Fase 5 (Hardening). Fase 3 entrega shortcode funcional. El bloque puede hacerse como PR-C separado sin bloquear el lanzamiento.
- El shortcode y el bloque son funcionalmente equivalentes para usuarios finales. WP.org no exige bloque Gutenberg.

### Decisión 3 (MENOR): ¿Upload multipart o base64?

- **Opción A (Multipart):** Fiel al plan, `Content-Type: multipart/form-data`. Más eficiente en bytes. Requiere más código PHP para construir el body.
- **Opción B (Base64 JSON):** `Content-Type: application/json`, archivo como base64. +33% payload pero código más simple. La API ya acepta base64 en OCR service.

---

## Estado: Ready for Proposal

Las 3 decisiones de §10 deben resolverse antes de la propuesta. La más crítica es la Decisión 1 (auth). Con las decisiones tomadas, el orden de implementación natural es:

```
A → Entry point + scaffolding + API Client
B → Settings wp-admin
C → Shortcode + AJAX handler + JS + semáforo
D → [Si aplica] Bloque Gutenberg
E → Historial widget
F → WooCommerce hook
G → i18n + Plugin Check
H → WP.org assets + readme.txt
I → GitHub Actions ZIP workflow
J → [Si aplica Decisión 1-A] API key middleware
```
