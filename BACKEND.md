# Unergy — Arquitectura Backend

Plataforma de contexto energético y posicionamiento espacial. Esta arquitectura se divide en dos servidores: un **servidor local** y un **servidor remoto**.

## Estructura del proyecto

```
hackaton-unergy/
├── wifi-positioning/        # Módulo WiFi original (referencia)
├── frontend/                # Aplicación SvelteKit
├── local-server/            # Backend principal (FastAPI)
│   ├── main.py              # Punto de entrada
│   ├── requirements.txt     # Dependencias Python
│   ├── app/
│   │   ├── core/
│   │   │   └── config.py            # Configuración central
│   │   ├── domain/
│   │   │   ├── user.py              # Modelo de Usuario
│   │   │   ├── space.py             # Modelo de Espacio
│   │   │   ├── device.py            # (placeholder) Dispositivo
│   │   │   ├── energy_event.py      # (placeholder) Evento energético
│   │   │   └── alert.py             # (placeholder) Alerta
│   │   ├── repositories/
│   │   │   ├── user_repository.py   # Persistencia mock de usuarios (in-memory)
│   │   │   └── space_repository.py  # Persistencia real de espacios (JSON en disco)
│   │   ├── services/
│   │   │   ├── auth_service.py      # Registro, login, JWT
│   │   │   ├── space_service.py     # Gestión de espacios
│   │   │   └── wifi_integration_service.py  # Wrapper de wifi-positioning
│   │   └── api/routes/
│   │       ├── auth.py              # POST /auth/register, /auth/login, GET /auth/me
│   │       ├── spaces.py            # POST /spaces, GET /spaces, GET /spaces/{id}
│   │       └── instructions.py      # GET /instructions/register-space, /instructions/wifi-status
│   ├── wifipos/                 # Copia del módulo wifi-positioning (scanner, model, storage)
│   ├── data/
│   │   └── spaces.json          # Persistencia de espacios (creado automáticamente)
│   └── tests/
│       ├── test_api.py              # 17 tests (endpoints)
│       └── test_persistence.py      # 34 tests (persistencia, WiFi, walk-mode, tracking, reset)
└── remote-server/           # Hub WebSocket en tiempo real
    ├── main.py              # Punto de entrada
    ├── requirements.txt     # Dependencias Python
    ├── app/ws/
    │   └── manager.py       # Gestor de conexiones WebSocket
    └── tests/
        └── test_ws.py       # 4 tests
```

## Cómo correr los servidores

### Requisitos previos

- Python 3.10+
- pip

### Instalar dependencias

```bash
pip install -r local-server/requirements.txt
pip install -r remote-server/requirements.txt
```

### Iniciar el servidor local (puerto 8000)

```bash
cd local-server
uvicorn main:app --reload --port 8000
```

### Iniciar el servidor remoto (puerto 8001)

```bash
cd remote-server
uvicorn main:app --reload --port 8001
```

### Ejecutar tests

```bash
# Tests del servidor local (51 tests: 17 endpoints + 34 persistencia/WiFi/tracking/reset)
cd local-server && python -m pytest tests/ -v

# Tests del servidor remoto (4 tests)
cd remote-server && python -m pytest tests/ -v
```

## API del servidor local

| Método | Ruta | Auth | Descripción |
|--------|------|------|-------------|
| `GET` | `/` | No | Health check |
| `POST` | `/auth/register` | No | Registrar usuario |
| `POST` | `/auth/login` | No | Iniciar sesión |
| `GET` | `/auth/me` | Sí | Obtener usuario actual |
| `GET` | `/instructions/register-space` | No | Instrucciones para registrar espacio |
| `GET` | `/instructions/wifi-status` | No | Estado del módulo WiFi |
| `POST` | `/spaces` | No | Registrar espacio (walk-mode, `samples` configurable) |
| `GET` | `/spaces` | No | Listar espacios |
| `GET` | `/spaces/{id}` | No | Obtener espacio por ID |
| `DELETE` | `/spaces/reset` | No | **Resetear todo** (espacios, fingerprints, modelos) |
| `POST` | `/tracking/start` | No | Iniciar tracking continuo (`interval` configurable) |
| `POST` | `/tracking/stop` | No | Detener tracking |
| `GET` | `/tracking/status` | No | Estado del tracking + última predicción |
| `GET` | `/tracking/predict` | No | Predicción única de ubicación |

### Ejemplo: Registrar usuario

```bash
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"usuario1","email":"user@example.com","password":"mipass123"}'
```

### Ejemplo: Registrar espacio

```bash
# Walk-mode con 20 muestras (por defecto, el usuario camina por el espacio)
curl -X POST http://localhost:8000/spaces \
  -H "Content-Type: application/json" \
  -d '{"name":"Cocina","space_type":"kitchen"}'

# Menos muestras para pruebas rápidas
curl -X POST http://localhost:8000/spaces \
  -H "Content-Type: application/json" \
  -d '{"name":"Sala","space_type":"living_room","samples":5}'
```

### Ejemplo: Tracking (predicción continua)

```bash
# Iniciar tracking con predicción cada 3 segundos
curl -X POST "http://localhost:8000/tracking/start?interval=3"

# Ver estado y última predicción
curl http://localhost:8000/tracking/status

# Predicción única (sin tracking continuo)
curl http://localhost:8000/tracking/predict

# Detener tracking
curl -X POST http://localhost:8000/tracking/stop
```

### Ejemplo: Resetear todo

```bash
# Borra todos los espacios, fingerprints WiFi y modelos entrenados
curl -X DELETE http://localhost:8000/spaces/reset
```

## WebSocket del servidor remoto

### Conectar

```javascript
const ws = new WebSocket("ws://localhost:8001/ws?client_id=mi-usuario");
```

### Enviar evento

```javascript
ws.send(JSON.stringify({
  type: "space_registered",
  payload: { space_name: "Cocina", user_id: "user-1" }
}));
```

### Recibir broadcast

```javascript
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  // { sender: "otro-usuario", type: "space_registered", payload: {...} }
};
```

### Tipos de eventos soportados

- `space_registered` — Nuevo espacio registrado
- `location_change` — Cambio de ubicación detectado
- `ping` — Keep-alive
- `client_disconnected` — Un cliente se desconectó (emitido por el servidor)

## Conexión frontend ↔ servidores

El frontend debe conectarse a **dos servidores distintos**:

```
Frontend (SvelteKit)
├── HTTP → http://localhost:8000  (servidor local — lógica de negocio)
└── WS   → ws://localhost:8001   (servidor remoto — tiempo real)
```

En `frontend/src/lib/config/constants.ts`:
```typescript
export const BACKEND_BASE_URL = 'http://localhost:8000';
export const REALTIME_WS_URL = 'ws://localhost:8001/ws';
```

## Integración con wifi-positioning/

El módulo `wifi-positioning/` se copia directamente en `local-server/wifipos/` para que pueda ser importado sin necesidad de instalación separada:

```
wifi-positioning/          ← Módulo original (referencia)
    └── src/wifipos/
        ├── scanner/       ← WifiScanner, WifiReading
        ├── model/         ← Predictor, Fingerprint
        └── storage/       ← Database

local-server/
    ├── wifipos/           ← Copia del módulo (importable directamente)
    │   ├── scanner/
    │   ├── model/
    │   └── storage/
    └── app/services/
        └── wifi_integration_service.py  ← Wrapper/adaptador
```

El servicio `WiFiIntegrationService` importa directamente desde `wifipos` (la copia local) y tiene una **cadena de escaneo con fallback**:

1. **wifipos scanner** — el módulo copiado localmente (scanner, predictor, database)
2. **nmcli nativo** — escaneo directo via NetworkManager (Linux)
3. **iwlist nativo** — escaneo directo via wireless-tools (Linux)
4. **Mock data** — último recurso para CI/testing sin WiFi

El campo `source` en los resultados indica qué método se usó:
- `"wifipos_scanner"` → módulo completo
- `"native_linux"` → nmcli o iwlist
- `"mock"` → datos de prueba

## Estado actual de la persistencia y datos

| Componente | Estado | Almacenamiento |
|-----------|--------|---------------|
| **Espacios** | ✅ Persistente | JSON en disco (`data/spaces.json`) — sobrevive reinicios |
| **Datos WiFi** | ✅ Real | Guardados con cada espacio — escaneo real via wifipos/nmcli/iwlist |
| **Huellas WiFi** | ✅ Persistente | SQLite (`data/wifipos.db`) — cada espacio guarda huella en tabla fingerprints |
| **Modelo ML** | ✅ Auto-train | Se entrena automáticamente al tener ≥2 ubicaciones con ≥3 huellas |
| **Usuarios** | ⚠️ In-memory | `UserRepository` — se pierde al reiniciar |

### Migrar usuarios a persistencia real

1. **Crear nueva implementación** del repositorio (e.g. `user_repository_sql.py`) que implemente los mismos métodos (`create`, `get_by_id`, `get_by_email`, etc.)
2. **Cambiar la instanciación** en `main.py` — reemplazar `UserRepository()` por `UserRepositorySQL(db_session)`
3. **No se necesita cambiar** servicios ni rutas — la interfaz es la misma

## Entidades preparadas para el futuro

Los modelos de dominio para estas entidades ya están definidos como placeholders:

- **Device** — Dispositivos IoT asociados a un espacio
- **EnergyEvent** — Lecturas de consumo, picos, anomalías
- **Alert** — Notificaciones por consumo alto, huella de carbono, etc.

Solo falta crear sus repositorios, servicios y rutas cuando se necesiten.
