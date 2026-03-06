# wifipos — Sistema de Posicionamiento Indoor por WiFi

Sistema de posicionamiento en interiores basado en huellas WiFi (*WiFi fingerprinting*). Aprende los patrones de señal WiFi en diferentes habitaciones y luego predice tu ubicación actual en tiempo real.

---

## 🚀 Inicio Rápido (después de clonar)

### 1. Instalar el proyecto

```bash
# Entrar al directorio del proyecto
cd wifi-positioning

# Instalar en modo desarrollo
pip install -e .
```

> **Nota macOS:** Si estás en macOS, instala también el soporte para Location Services:
> ```bash
> pip install -e ".[macos]"
> ```

> **Nota desarrollo:** Para correr los tests, instala las dependencias de desarrollo:
> ```bash
> pip install -e ".[dev]"
> ```

### 2. Verificar la instalación

```bash
wifipos --help
```

Deberías ver la lista de comandos disponibles.

---

## 📡 Tomar muestras: cuarto, cocina y sala

Para que el sistema funcione necesitas **recolectar muestras WiFi** en cada ubicación. Camina a cada habitación y ejecuta los siguientes comandos:

### Paso 1: Aprender cada ubicación

**Ve al cuarto** y ejecuta:
```bash
wifipos learn cuarto --samples 10 --interval 2
```

**Ve a la cocina** y ejecuta:
```bash
wifipos learn cocina --samples 10 --interval 2
```

**Ve a la sala** y ejecuta:
```bash
wifipos learn sala --samples 10 --interval 2
```

Verás una barra de progreso mientras se recolectan las muestras.

#### ¿Qué significan `--samples 10` y `--interval 2`?

| Parámetro | Qué hace | Ejemplo |
|-----------|----------|---------|
| `--samples N` (o `-s N`) | **Cuántas muestras WiFi tomar.** Cada muestra es un escaneo completo de todas las redes WiFi visibles y sus intensidades de señal (RSSI). Con `--samples 10` el sistema escanea 10 veces las redes WiFi desde esa ubicación. | `--samples 10` → 10 escaneos WiFi |
| `--interval S` (o `-i S`) | **Segundos de espera entre cada muestra.** Le da tiempo a las señales WiFi de variar naturalmente (las señales fluctúan por personas moviéndose, puertas abriéndose, etc). Con `--interval 2` espera 2 segundos entre cada escaneo. | `--interval 2` → 2 segundos entre escaneos |

**Ejemplo concreto:** `wifipos learn cocina --samples 10 --interval 2` significa:
> *"Escanea las redes WiFi 10 veces desde la cocina, esperando 2 segundos entre cada escaneo"* (toma ~20 segundos en total).

**¿Cuántas muestras necesito?**
- **10 muestras** → suficiente para probar rápido
- **15-20 muestras** → recomendado para buena precisión
- **30+ muestras** → máxima precisión (toma más tiempo)

> **💡 Tip:** Si las predicciones no son precisas, vuelve a cada habitación y toma más muestras con `--samples 20`. Las muestras nuevas se suman a las anteriores.

### Paso 2: Verificar las muestras recolectadas

```bash
wifipos locations
```

Deberías ver algo como:
```
┌──────────┬──────────────┐
│ Location │ Fingerprints │
├──────────┼──────────────┤
│ cocina   │           10 │
│ cuarto   │           10 │
│ sala     │           10 │
└──────────┴──────────────┘
Total: 3 locations, 30 fingerprints
```

### Paso 3: Entrenar el modelo

```bash
wifipos train
```

Esto entrena un clasificador RandomForest y muestra la precisión por validación cruzada. Verás una tabla comparando RandomForest, KNN y GradientBoosting.

### Paso 4: Predecir tu ubicación

**Predicción única** — te dice dónde estás ahora:
```bash
wifipos predict
```

**Predicción continua** — rastrea tu ubicación en tiempo real:
```bash
wifipos track --interval 3
```
Presiona `Ctrl+C` para detener el rastreo.

---

## 📋 Todos los comandos

| Comando | Descripción |
|---------|-------------|
| `wifipos learn <ubicación> --samples N --interval S` | Recolectar N muestras WiFi en una ubicación |
| `wifipos train` | Entrenar el modelo con las muestras recolectadas |
| `wifipos predict` | Predecir ubicación actual (una vez) |
| `wifipos track --interval S` | Predecir ubicación continuamente cada S segundos |
| `wifipos locations` | Ver ubicaciones aprendidas y cantidad de muestras |
| `wifipos forget <ubicación>` | Eliminar datos de una ubicación |
| `wifipos status` | Ver información del modelo (precisión, ubicaciones) |
| `wifipos export datos.csv` | Exportar muestras a un archivo CSV |
| `wifipos reset --confirm` | Eliminar todos los datos |

---

## 🔧 Solución de problemas

### Linux: "Permission denied" o escaneo vacío

- Intenta con `sudo`: `sudo wifipos learn cuarto`
- Agrega tu usuario al grupo netdev: `sudo usermod -aG netdev $USER`
- Verifica que NetworkManager esté corriendo: `systemctl status NetworkManager`

### macOS: "No networks found" o BSSID/SSID retorna None

- Habilita Location Services para tu terminal en **Preferencias del Sistema > Privacidad y Seguridad > Servicios de Localización**.

### Windows: "WiFi is turned off"

- Activa WiFi en **Configuración > Red e Internet > Wi-Fi**.

### Baja precisión en predicciones

- Recolecta más muestras por ubicación (15-20 recomendado).
- Asegúrate de que las ubicaciones sean físicamente distintas (diferentes habitaciones).
- Vuelve a entrenar después de recolectar más datos: `wifipos train`.

---

## 📁 Estructura del proyecto

```
wifi-positioning/
├── pyproject.toml           # Configuración del paquete Python
├── README.md                # Documentación técnica en inglés
├── src/wifipos/
│   ├── cli.py               # Interfaz de línea de comandos (typer + rich)
│   ├── scanner/
│   │   ├── base.py          # Clase base abstracta del scanner
│   │   ├── macos.py         # Scanner macOS (CoreWLAN)
│   │   ├── linux.py         # Scanner Linux (nmcli / iwlist)
│   │   └── windows.py       # Scanner Windows (netsh)
│   ├── model/
│   │   ├── fingerprint.py   # Recolección de huellas WiFi
│   │   ├── trainer.py       # Entrenamiento del modelo ML
│   │   └── predictor.py     # Predicción en tiempo real
│   ├── storage/
│   │   └── database.py      # Base de datos SQLite
│   └── utils/
│       └── platform.py      # Detección de SO y fábrica de scanners
├── tests/                   # Tests unitarios
└── data/                    # Directorio para datos
```

## 🧪 Correr tests

```bash
cd wifi-positioning
pip install -e ".[dev]"
python -m pytest tests/ -v
```

## ⚙️ Cómo funciona

1. **Fase de aprendizaje**: Caminas a cada habitación y el sistema graba las señales WiFi visibles. Cada ubicación obtiene una "huella" única — el conjunto de puntos de acceso y sus intensidades de señal (RSSI).
2. **Fase de entrenamiento**: Un modelo de machine learning (RandomForest) aprende la relación entre los patrones de señal WiFi y las ubicaciones.
3. **Fase de predicción**: Cuando quieres saber dónde estás, el sistema escanea las señales WiFi actuales y usa el modelo entrenado para predecir tu ubicación.

## 🤝 Contribuir

1. Haz fork del repositorio
2. Crea una rama: `git checkout -b feature/mi-feature`
3. Haz tus cambios y agrega tests
4. Corre los tests: `pytest`
5. Envía un pull request