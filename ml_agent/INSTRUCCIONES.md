# 🛒 ML Agent — Instrucciones de Configuración

## Paso 1: Instalá las dependencias

Abrí una terminal en esta carpeta y ejecutá:

```bash
pip install requests
```

## Paso 2: Configurá tus credenciales

```bash
python ml_setup.py
```

Te va a pedir:
- **App ID** (client_id): lo encontrás en https://developers.mercadolibre.com.ar → Mis apps
- **Secret Key** (client_secret): idem
- **Redirect URI**: la misma que configuraste en tu app de ML (ej: `https://localhost`)

Esto guarda un archivo `ml_config.json` en esta carpeta.

## Paso 3: Autorizá la app (solo la primera vez)

```bash
python ml_setup.py --authorize
```

- Se abre tu navegador en la pantalla de autorización de ML
- Hacés clic en "Permitir"
- ML te redirige a tu Redirect URI con un `?code=TG-XXXX`
- Copiás esa URL completa y la pegás en la terminal
- Listo — los tokens quedan guardados en `ml_tokens.json`

**Esto se hace UNA SOLA VEZ.** Después el agente renueva los tokens automáticamente.

## Paso 4: Verificá que todo funcione

```bash
python ml_setup.py --check
```

Deberías ver:
```
✅ Credenciales: client_id=XXXXXXXX***
✅ Tokens encontrados. User ID: 123456789
✅ Conexión a ML API OK. Vendedor: TU_NICK
```

## Paso 5: Correlo por primera vez

```bash
python ml_main.py
```

Esto:
1. Descarga todos tus datos de los últimos 30 días
2. Genera 4 dashboards HTML en la carpeta `dashboards/`

Para cambiar el período:
```bash
python ml_main.py --days 60
```

## Paso 6: Dashboards generados

Abrí los archivos en la carpeta `dashboards/`:
- `dashboard_ventas.html` — GMV, unidades, ticket promedio, evolución diaria
- `dashboard_stock.html` — Stock Flex/Full, quiebres, ítems críticos
- `dashboard_comisiones.html` — Comisiones ML, costos de envío, neto
- `dashboard_reclamos.html` — Reclamos abiertos, devoluciones, tasas

---

## Ejecución automática (configurada desde Cowork)

El scheduler de Cowork corre `ml_main.py` todos los días a las 8am.
Los dashboards se actualizan automáticamente.

Para cambiar la hora o frecuencia, pedíselo a Cowork.

---

## Estructura de archivos

```
ml_agent/
├── ml_auth.py          # OAuth y manejo de tokens
├── ml_data.py          # Fetchers de la API de ML
├── ml_dashboard.py     # Generador de HTML dashboards
├── ml_main.py          # Script orquestador principal
├── ml_setup.py         # Configuración inicial
├── ml_config.json      # Credenciales (NO compartir)
├── ml_tokens.json      # Tokens OAuth (NO compartir)
├── data/               # JSONs con los datos descargados
└── dashboards/         # HTMLs generados
```

---

## Seguridad

- `ml_config.json` y `ml_tokens.json` contienen información sensible
- No los subas a Git ni los compartas
- Están en esta carpeta local de tu máquina
