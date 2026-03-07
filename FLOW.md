# Flujo completo de la aplicación — Unergy

Este documento describe cómo funciona el flujo de datos entre todos los componentes de la plataforma.

---

## ¿Cómo funciona? — Resumen para el usuario

### ¿Qué hace la app?

Unergy permite **registrar espacios** (cocina, sala, oficina, etc.) usando señales WiFi como huella digital. Cada espacio en tu casa u oficina tiene un patrón único de redes WiFi cercanas — la app aprovecha esto para saber en qué habitación estás.

### Flujo desde el punto de vista del usuario

```
📱 USUARIO
    │
    │ 1. Abre la app (http://localhost:5173)
    │
    │ 2. Va a la cocina y presiona "Registrar espacio"
    │    → Escribe "Cocina" y selecciona tipo "kitchen"
    │    → El sistema escanea las redes WiFi del entorno
    │    → Guarda la "huella WiFi" de la cocina
    │
    │ 3. Va a la sala y registra otro espacio "Sala"
    │    → Mismo proceso: escanea WiFi y guarda huella
    │
    │ 4. Después de registrar ≥2 espacios con ≥3 registros cada uno:
    │    → El sistema AUTOMÁTICAMENTE entrena un modelo ML
    │    → Ahora puede predecir en qué habitación estás
    │
    │ 5. Consulta "¿Dónde estoy?"
    │    → El sistema escanea WiFi y compara con las huellas
    │    → Responde: "Cocina (95% confianza)"
    │
    └─ Todos los datos se guardan en disco (JSON + SQLite)
       → Sobreviven reinicios del servidor ✓
```

### ¿Qué pasa internamente cuando registras un espacio?

1. **Escaneo WiFi inicial** — Captura todas las redes cercanas (BSSID, SSID, señal, canal) para los metadatos del espacio
2. **Guardar espacio** — Se guarda en `data/spaces.json` con los datos WiFi
3. **Walk-mode (movimiento)** — Se toman **20 muestras** (configurable con `samples`) mientras el usuario camina por el espacio. Cada muestra captura las señales WiFi desde una posición ligeramente diferente, lo que mejora la precisión del modelo
4. **Guardar huellas** — Cada muestra se guarda como fingerprint en `data/wifipos.db` (SQLite) — equivale a `wifipos learn --walk`
5. **Auto-entrenar** — Si ya hay suficientes datos (≥2 ubicaciones con ≥3 huellas), entrena automáticamente un modelo ML — equivale a `wifipos train`

### ¿Cómo se usa el módulo `wifipos`?

El módulo `wifi-positioning/` (que ya estaba en el repo) se copió a `local-server/wifipos/` para poder importarlo directamente. No hace falta instalarlo con pip. El servidor local lo usa así:

| Operación | Equivale a CLI | Cuándo pasa |
|-----------|----------------|-------------|
| `collect_and_save_fingerprints()` | `wifipos learn cocina --walk` | Al registrar un espacio (20 muestras con movimiento) |
| `try_train_model()` | `wifipos train` | Automático después de cada registro si hay ≥2 ubicaciones con ≥3 huellas |
| `start_tracking()` / `stop_tracking()` | `wifipos track` | `POST /tracking/start` y `POST /tracking/stop` |
| `get_current_location()` | `wifipos predict` | `GET /tracking/predict` — predicción única |
| `reset_wifi_data()` | `wifipos reset` | `DELETE /spaces/reset` — borra todo |

### ¿Dónde se guardan los datos?

| Dato | Archivo | Formato |
|------|---------|---------|
| Espacios registrados | `local-server/data/spaces.json` | JSON |
| Huellas WiFi | `local-server/data/wifipos.db` | SQLite (tabla `fingerprints`) |
| Modelo ML entrenado | `local-server/data/wifipos.db` | SQLite (tabla `models`, blob serializado) |
| Usuarios | En memoria | Se pierde al reiniciar (mock) |

---

## Diagrama general

```
┌─────────────────────────────────────────────────────────────┐
│                    FRONTEND (SvelteKit :5173)                │
│                                                             │
│  SpaceService ─── HTTP ──→ POST/GET /spaces                │
│  InstructionsService ── HTTP ──→ GET /instructions/*       │
│  WebSocket client ── WS ──→ ws://localhost:8001/ws         │
└────────────┬──────────────────────────────────┬─────────────┘
             │ HTTP REST                        │ WebSocket
             ▼                                  ▼
┌────────────────────────────┐    ┌──────────────────────────┐
│  LOCAL SERVER (FastAPI :8000)│   │ REMOTE SERVER (WS :8001) │
│                              │   │                          │
│  Rutas:                      │   │ Endpoint: /ws            │
│  ├── /spaces                 │   │ ConnectionManager        │
│  ├── /instructions           │   │ Broadcast a todos        │
│  └── /auth                   │   │                          │
│                              │   └──────────────────────────┘
│  Servicios:                  │
│  ├── SpaceService            │
│  ├── WiFiIntegrationService  │
│  └── AuthService             │
│                              │
│  Persistencia:               │
│  └── data/spaces.json        │ ← Archivo JSON en disco
└────────────────────────────┘
```

---

## Flujo 1: Registrar un espacio nuevo

Este es el flujo principal. El usuario crea un espacio y el sistema captura automáticamente múltiples muestras WiFi del entorno **mientras el usuario se mueve** (walk mode), **guarda todas las huellas WiFi** en la base de datos, y **entrena automáticamente** el modelo de posicionamiento.

### Paso a paso:

```
USUARIO                  FRONTEND                    LOCAL SERVER
  │                        │                            │
  │ Clic "Nuevo Espacio"  │                            │
  │ ─────────────────────→│                            │
  │                        │                            │
  │ Escribe "Cocina"      │                            │
  │ Selecciona "kitchen"  │                            │
  │ Clic "Confirmar"      │                            │
  │ ─────────────────────→│                            │
  │                        │ POST /spaces               │
  │                        │ { name: "Cocina",          │
  │                        │   space_type: "kitchen",   │
  │                        │   samples: 20 }            │
  │                        │ ──────────────────────────→│
  │                        │                            │
  │  ¡Camina por el       │                    ┌───────┤
  │   espacio mientras    │                    │ 1. SpaceService.register_space()
  │   se recolectan       │                    │
  │   muestras!           │                    │ 2. WiFi scan inicial (metadata):
  │                        │                    │    wifipos scanner → nmcli
  │                        │                    │    → iwlist → mock
  │                        │                    │
  │                        │                    │ 3. SpaceRepository.create()
  │                        │                    │    → Guarda en data/spaces.json
  │                        │                    │
  │                        │                    │ 4. collect_and_save_fingerprints()
  │                        │                    │    → 20 escaneos WiFi con
  │                        │                    │      movimiento (walk mode)
  │                        │                    │    → Cada uno se guarda en
  │                        │                    │      data/wifipos.db (SQLite)
  │                        │                    │    (equivale a wifipos learn --walk)
  │                        │                    │
  │                        │                    │ 5. try_train_model()
  │                        │                    │    Si hay ≥2 ubicaciones con
  │                        │                    │    ≥3 huellas cada una:
  │                        │                    │    → Entrena modelo ML
  │                        │                    │    (equivale a `wifipos train`)
  │                        │                    └───────┤
  │                        │                            │
  │                        │ ←──────────────────────────│
  │                        │ 200 OK                     │
  │                        │ { id: 1,                   │
  │                        │   name: "Cocina",          │
  │                        │   space_type: "kitchen",   │
  │                        │   wifi_metadata: {         │
  │                        │     networks_detected: 5,  │
  │                        │     source: "native_linux",│
  │                        │     readings: [...]        │
  │                        │   },                       │
  │                        │   created_at: "..." }      │
  │ ←─────────────────────│                            │
  │ Se muestra la tarjeta │                            │
  │ del espacio con los   │                            │
  │ datos WiFi reales     │                            │
```

### Cadena de escaneo WiFi (prioridad):

| Prioridad | Método | Cuándo se usa | Datos |
|-----------|--------|--------------|-------|
| 1° | `wifipos` scanner | Módulo copiado en `local-server/wifipos/` | BSSID, SSID, RSSI (dBm), Channel — escaneo nativo de la plataforma (macOS CoreWLAN, Linux nmcli) |
| 2° | `nmcli` nativo | Linux con NetworkManager, sin scanner disponible | Mismos campos, conversión signal% → dBm |
| 3° | `iwlist` nativo | Linux con wireless-tools, sin nmcli | Parseo de salida iwlist |
| 4° | Mock data | CI/testing, sin WiFi hardware | 3 redes ficticias con `source: "mock"` |

El campo `source` en `wifi_metadata` siempre indica qué método se usó:
- `"wifipos_scanner"` — módulo completo
- `"native_linux"` — nmcli o iwlist directo
- `"mock"` — datos de prueba

### Flujo de datos wifipos (learn → train → predict → track → reset):

```
POST /spaces (samples=20) → scan WiFi → guardar espacio
                     │
                     ▼
          collect_and_save_fingerprints()  ← equivale a `wifipos learn --walk`
          → 20 escaneos WiFi con movimiento
          → 20x INSERT INTO fingerprints   (SQLite: data/wifipos.db)
                     │
                     ▼
          try_train_model()               ← equivale a `wifipos train`
          ├── ¿≥2 ubicaciones con ≥3 huellas?
          │   ├── NO → skip (aún no hay suficientes datos)
          │   └── SÍ → Entrenar modelo ML:
          │       1. augment_fingerprints (ruido ±3 dB)
          │       2. build_feature_matrix (BSSIDs → columnas)
          │       3. Probar RandomForest, KNN, GradientBoosting
          │       4. Seleccionar mejor por cross-validation
          │       5. Serializar con joblib → BLOB
          │       6. INSERT INTO models (SQLite)
          └────────────────────────────────────────

GET /tracking/predict                    ← equivale a `wifipos predict`
          │
          ▼
   Predictor.predict(scanner)
   1. scan_averaged(3 escaneos)
   2. Construir vector de features
   3. pipeline.predict_proba()
   4. → { location: "Cocina", confidence: 0.95 }

POST /tracking/start                     ← equivale a `wifipos track`
          │
          ▼
   Background thread:
   while active:
     predict() → actualizar latest_prediction
     sleep(interval)

DELETE /spaces/reset                     ← equivale a `wifipos reset`
          │
          ▼
   1. Detener tracking (si activo)
   2. SpaceRepository.delete_all() → vaciar spaces.json
   3. Database.reset() → DROP fingerprints + models (SQLite)
```

---

## Flujo 2: Listar espacios

```
FRONTEND                    LOCAL SERVER                 DISCO
  │                            │                          │
  │ GET /spaces                │                          │
  │ ──────────────────────────→│                          │
  │                            │ SpaceService             │
  │                            │ .list_spaces(user_id=1)  │
  │                            │ ↓                        │
  │                            │ SpaceRepository          │
  │                            │ .list_by_user(1)         │
  │                            │ ↓                        │
  │                            │ Lee de memoria           │
  │                            │ (cargado desde JSON      │
  │                            │  al iniciar el servidor) │
  │                            │                          │
  │ ←──────────────────────────│                          │
  │ 200 OK                     │                          │
  │ [ { id: 1, name: "Cocina", │                          │
  │     wifi_metadata: {...},  │                          │
  │     ... },                 │                          │
  │   { id: 2, name: "Sala",  │                          │
  │     wifi_metadata: {...},  │                          │
  │     ... } ]                │                          │
```

---

## Flujo 3: Persistencia de datos

Los espacios se guardan en `local-server/data/spaces.json`:

```json
{
  "next_id": 3,
  "spaces": {
    "1": {
      "id": 1,
      "user_id": 1,
      "name": "Cocina",
      "space_type": "kitchen",
      "wifi_metadata": {
        "networks_detected": 5,
        "source": "native_linux",
        "readings": [
          {
            "bssid": "AA:BB:CC:DD:EE:01",
            "ssid": "MiRedWiFi",
            "rssi": -45,
            "channel": 6
          },
          {
            "bssid": "AA:BB:CC:DD:EE:02",
            "ssid": "Vecino_5G",
            "rssi": -72,
            "channel": 36
          }
        ]
      },
      "created_at": "2026-03-07T01:00:00.123456"
    }
  }
}
```

### Ciclo de vida de la persistencia:

```
Servidor inicia
    │
    ▼
SpaceRepository.__init__()
    │
    ├── ¿Existe data/spaces.json?
    │   ├── SÍ → Carga espacios y next_id desde el archivo
    │   └── NO → Inicia vacío (next_id=1, spaces={})
    │
WiFiIntegrationService.__init__()
    │
    ├── Abre/crea data/wifipos.db (SQLite)
    │   → Tabla fingerprints (huellas WiFi)
    │   → Tabla models (modelos ML entrenados)
    │
    ▼
Servidor corriendo...
    │
    ├── POST /spaces → SpaceService.register_space()
    │   ├── Escanea WiFi
    │   ├── Guarda espacio → data/spaces.json
    │   ├── Guarda huella → data/wifipos.db (fingerprints)
    │   └── Intenta entrenar modelo → data/wifipos.db (models)
    │
    ├── DELETE /spaces/{id} → SpaceRepository.delete()
    │   └── Elimina espacio → _save() → Escribe JSON a disco
    │
    └── GET /spaces → SpaceRepository.list_by_user()
        └── Lee de memoria (ya cargado)

Servidor se reinicia
    │
    ▼
Todos los datos persisten ✓
    ├── Espacios (data/spaces.json)
    ├── Huellas WiFi (data/wifipos.db)
    └── Modelo ML entrenado (data/wifipos.db)
```

---

## Flujo 4: Estado del WiFi

```
FRONTEND                    LOCAL SERVER
  │                            │
  │ GET /instructions/         │
  │     wifi-status            │
  │ ──────────────────────────→│
  │                            │ WiFiIntegrationService
  │                            │ .scan_current_environment()
  │                            │ ↓ (ejecuta el escaneo)
  │ ←──────────────────────────│
  │ {                          │
  │   wifi_available: true,    │  ← true si source ≠ "mock"
  │   source: "native_linux",  │
  │   networks_detected: 5     │
  │ }                          │
```

---

## Flujo 5: WebSocket — Eventos en tiempo real

```
FRONTEND A                 REMOTE SERVER              FRONTEND B
  │                            │                          │
  │ ws://localhost:8001/ws     │                          │
  │ ?client_id=user-a          │   ws://.../ws            │
  │ ──────────────────────────→│ ←────────────────────────│
  │                            │   ?client_id=user-b      │
  │                            │                          │
  │ send({                     │                          │
  │   type: "space_registered",│                          │
  │   payload: {               │                          │
  │     space_name: "Cocina"   │                          │
  │   }                        │                          │
  │ })                         │                          │
  │ ──────────────────────────→│                          │
  │                            │ broadcast (excluye A)    │
  │                            │ ────────────────────────→│
  │                            │                          │ onmessage:
  │                            │                          │ { sender: "user-a",
  │                            │                          │   type: "space_registered",
  │                            │                          │   payload: {...} }
```

---

## Resumen de tecnologías y estado actual

| Componente | Estado | Persistencia | WiFi |
|-----------|--------|-------------|------|
| **Espacios** | ✅ Real | JSON en disco (`data/spaces.json`) | Datos WiFi reales guardados con cada espacio |
| **Huellas WiFi** | ✅ Walk-mode | SQLite (`data/wifipos.db`) | 20 muestras con movimiento por espacio |
| **Modelo ML** | ✅ Auto-train | SQLite (`data/wifipos.db`) | Se entrena automáticamente al tener ≥2 ubicaciones con ≥3 huellas |
| **Tracking** | ✅ Real | Background thread | `POST /tracking/start` / `POST /tracking/stop` |
| **Reset** | ✅ Real | Borra todo | `DELETE /spaces/reset` — espacios + fingerprints + modelos |
| **WiFi scan** | ✅ Real | N/A | wifipos → nmcli → iwlist → mock |
| **Usuarios** | ⚠️ Mock | In-memory | N/A |

---

## Cómo ejecutar el flujo completo

```bash
# Terminal 1: Servidor local
cd local-server
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Terminal 2: Servidor remoto
cd remote-server
pip install -r requirements.txt
uvicorn main:app --reload --port 8001

# Terminal 3: Frontend
cd frontend
pnpm install && pnpm dev
```

Abrir **http://localhost:5173** y registrar espacios. Por cada espacio:
1. Se toman **20 muestras WiFi** mientras caminas por el espacio (walk mode)
2. Todas las huellas se guardan en `data/wifipos.db`
3. Cuando hay ≥2 ubicaciones con ≥3 registros, el modelo se entrena automáticamente
4. **Iniciar tracking** para predicción continua de ubicación
5. **Resetear todo** con `curl -X DELETE http://localhost:8000/spaces/reset`
