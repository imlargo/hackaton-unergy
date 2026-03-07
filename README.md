# Unergy — Plataforma de Contexto Energético y Posicionamiento Espacial

Plataforma que permite registrar espacios (casa, oficina, negocio) usando posicionamiento por WiFi, con arquitectura preparada para dispositivos IoT, consumo energético y huella de carbono.

---

## 📁 Estructura del proyecto

```
hackaton-unergy/
├── frontend/            ← Aplicación web (SvelteKit + Tailwind)
├── local-server/        ← Backend principal (FastAPI, puerto 8000)
├── remote-server/       ← Hub en tiempo real (FastAPI + WebSocket, puerto 8001)
└── wifi-positioning/    ← Módulo de posicionamiento WiFi (solo lectura)
```

| Componente | Tecnología | Puerto | Rol |
|-----------|-----------|--------|-----|
| **Frontend** | SvelteKit, Tailwind, TypeScript | 5173 | Interfaz de usuario |
| **Servidor local** | FastAPI, Python | 8000 | API REST: auth, espacios, WiFi |
| **Servidor remoto** | FastAPI, WebSocket | 8001 | Eventos en tiempo real |
| **WiFi module** | Python, scikit-learn | — | Posicionamiento indoor (CLI/lib) |

---

## 🚀 Inicio rápido — Montar todo

### Requisitos previos

- **Python 3.10+** con pip
- **Node.js 18+** con pnpm (`npm install -g pnpm`)

### Paso 1: Clonar el repositorio

```bash
git clone https://github.com/imlargo/hackaton-unergy.git
cd hackaton-unergy
```

### Paso 2: Instalar dependencias del backend

```bash
# Dependencias del servidor local (INCLUYE scikit-learn, joblib, numpy para wifipos)
cd local-server
pip install -r requirements.txt
cd ..

# Dependencias del servidor remoto
pip install -r remote-server/requirements.txt
```

> ⚠️ **Importante:** `pip install -r local-server/requirements.txt` instala **todo** lo necesario
> para que el módulo de posicionamiento WiFi funcione (joblib, scikit-learn, numpy).
> No es necesario instalar `wifi-positioning/` por separado — ya está copiado
> dentro de `local-server/wifipos/`.
>
> Si ves el error `wifipos database not available — fingerprint not saved`,
> significa que las dependencias no están instaladas. Revisa con:
> ```bash
> curl http://localhost:8000/health/wifipos
> ```

### Paso 3: Instalar dependencias del frontend

```bash
cd frontend
pnpm install
cd ..
```

### Paso 4: Iniciar los tres servicios

Abre **tres terminales** desde la raíz del proyecto:

**Terminal 1 — Servidor local (API REST)**
```bash
cd local-server
uvicorn main:app --reload --port 8000
```

**Terminal 2 — Servidor remoto (WebSocket)**
```bash
cd remote-server
uvicorn main:app --reload --port 8001
```

**Terminal 3 — Frontend**
```bash
cd frontend
pnpm dev
```

### Paso 5: Abrir la aplicación

Abre tu navegador en: **http://localhost:5173**

Los servidores backend estarán disponibles en:
- API REST: http://localhost:8000 (documentación interactiva en http://localhost:8000/docs)
- WebSocket: ws://localhost:8001/ws

---

## ✅ Verificar que todo funciona

### Health checks rápidos

```bash
# Servidor local
curl http://localhost:8000/
# → {"service":"Unergy Local Server","version":"0.1.0","status":"running",...}

# Servidor remoto
curl http://localhost:8001/
# → {"service":"Unergy Remote Server","version":"0.1.0","status":"running","active_connections":0}
```

### Probar el flujo completo

```bash
# 1. Ver instrucciones para registrar espacio
curl http://localhost:8000/instructions/register-space

# 2. Registrar un espacio con walk-mode (20 muestras por defecto)
curl -X POST http://localhost:8000/spaces \
  -H "Content-Type: application/json" \
  -d '{"name":"Cocina","space_type":"kitchen"}'

# 2b. Registrar con menos muestras (más rápido para pruebas)
curl -X POST http://localhost:8000/spaces \
  -H "Content-Type: application/json" \
  -d '{"name":"Sala","space_type":"living_room","samples":5}'

# 3. Listar espacios
curl http://localhost:8000/spaces

# 4. Iniciar tracking continuo
curl -X POST "http://localhost:8000/tracking/start?interval=3"

# 5. Ver estado del tracking y última predicción
curl http://localhost:8000/tracking/status

# 6. Predicción única
curl http://localhost:8000/tracking/predict

# 7. Detener tracking
curl -X POST http://localhost:8000/tracking/stop

# 8. Resetear todo (espacios, fingerprints, modelos)
curl -X DELETE http://localhost:8000/spaces/reset
```

---

## 🧪 Ejecutar tests

```bash
# Tests del servidor local (51 tests: 17 endpoints + 34 persistencia/WiFi/tracking/reset)
cd local-server
python -m pytest tests/ -v

# Tests del servidor remoto (4 tests)
cd remote-server
python -m pytest tests/ -v

# Tests del módulo WiFi (64 tests)
cd wifi-positioning
pip install -e ".[dev]"
python -m pytest tests/ -v

# Tests del frontend
cd frontend
pnpm test:unit -- --run
```

---

## 🔌 Conexión frontend ↔ servidores

El frontend se conecta a **dos servidores** simultáneamente:

```
Frontend (SvelteKit, :5173)
├── HTTP → http://localhost:8000  ← Servidor local (auth, espacios, lógica de negocio)
└── WS   → ws://localhost:8001/ws ← Servidor remoto (eventos en tiempo real)
```

La configuración de URLs está en `frontend/src/lib/config/constants.ts`:

```typescript
export const BACKEND_BASE_URL = 'http://localhost:8000';
export const REALTIME_WS_URL = 'ws://localhost:8001/ws';
```

---

## 📡 API del servidor local

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

> 📖 Documentación interactiva (Swagger): **http://localhost:8000/docs**

---

## 🔄 WebSocket — Servidor remoto

### Conectar desde JavaScript

```javascript
const ws = new WebSocket("ws://localhost:8001/ws?client_id=mi-usuario");

// Enviar evento
ws.send(JSON.stringify({
  type: "space_registered",
  payload: { space_name: "Cocina", user_id: "user-1" }
}));

// Recibir broadcast
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log(data);
  // { sender: "otro-usuario", type: "space_registered", payload: {...} }
};
```

**Tipos de eventos:** `space_registered`, `location_change`, `ping`, `client_disconnected`

---

## 📡 Módulo WiFi — Posicionamiento indoor

El módulo `wifi-positioning/` es un sistema independiente de posicionamiento por huellas WiFi. Se consume desde el servidor local a través de un wrapper (`wifi_integration_service.py`) **sin modificar el módulo original**.

### Uso directo por CLI

```bash
cd wifi-positioning && pip install -e .

# Aprender ubicaciones (ir a cada habitación)
wifipos learn cocina --samples 10 --interval 2
wifipos learn sala --samples 10 --interval 2
wifipos learn cuarto --samples 10 --interval 2

# Entrenar modelo
wifipos train

# Predecir ubicación actual
wifipos predict

# Rastreo continuo
wifipos track --interval 3
```

> **Nota:** Sin WiFi real (CI, servidores remotos), el sistema usa datos mock automáticamente.

---

## 🗄️ Estado actual — Persistencia y datos reales

| Componente | Estado | Almacenamiento |
|-----------|--------|---------------|
| **Espacios** | ✅ Persistente | JSON en disco (`local-server/data/spaces.json`) — sobrevive reinicios |
| **Datos WiFi** | ✅ Real | Captura real de redes cercanas (wifipos → nmcli → iwlist → mock como último recurso) |
| **Huellas WiFi** | ✅ Persistente | SQLite (`data/wifipos.db`) — cada espacio guarda su huella WiFi |
| **Modelo ML** | ✅ Auto-train | Se entrena automáticamente al tener ≥2 ubicaciones con ≥3 huellas cada una |
| **Usuarios** | ⚠️ In-memory (`UserRepository`) | Se pierde al reiniciar — migrar a SQLAlchemy para producción |

### Cadena de escaneo WiFi

Al registrar un espacio, el servidor captura automáticamente las redes WiFi cercanas con esta prioridad:

1. **wifipos scanner** — módulo completo si está instalado
2. **nmcli** — NetworkManager CLI nativo (Linux)
3. **iwlist** — wireless-tools nativo (Linux)
4. **Mock data** — último recurso (CI/testing)

El campo `source` en `wifi_metadata` siempre indica qué método se usó.

### Migrar usuarios a persistencia real

1. Crear nueva implementación del repositorio (e.g. `user_repository_sql.py`)
2. Cambiar instanciación en `main.py`: `UserRepository()` → `UserRepositorySQL(session)`
3. Servicios y rutas **no cambian** — misma interfaz

---

## 🔧 Solución de problemas

| Problema | Solución |
|----------|----------|
| `command not found: uvicorn` | `pip install uvicorn` |
| `command not found: pnpm` | `npm install -g pnpm` |
| `Address already in use :8000` | Cerrar el proceso anterior o usar otro puerto: `--port 8002` |
| `ModuleNotFoundError: wifipos` | Normal — el servidor usa datos mock. Para WiFi real: `pip install -e wifi-positioning/` |
| macOS: "No networks found" | Habilitar Location Services en Preferencias del Sistema |
| Linux: "Permission denied" WiFi | `sudo usermod -aG netdev $USER` y reiniciar sesión |
| Frontend no conecta al backend | Verificar que el servidor local corre en puerto 8000 |

---

## 📖 Documentación adicional

- **[FLOW.md](./FLOW.md)** — Flujo completo de la aplicación (diagramas, paso a paso)
- **[BACKEND.md](./BACKEND.md)** — Arquitectura detallada del backend, modelos de dominio y guía de migración
- **[wifi-positioning/README.md](./wifi-positioning/README.md)** — Documentación técnica del módulo de posicionamiento WiFi