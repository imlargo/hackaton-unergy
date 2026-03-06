# wifipos

A modern, cross-platform WiFi fingerprinting-based indoor positioning system in Python. Think of it as a modern, maintained replacement for the abandoned [`whereami`](https://github.com/kootenpv/whereami) library.

**wifipos** learns WiFi signal patterns in different rooms or locations and then predicts your current location based on real-time WiFi scans, all offline and on your machine.

## Features

- **Cross-platform**: Works on macOS, Linux, and Windows
- **Machine learning**: Uses scikit-learn (RandomForest, KNN, GradientBoosting) for accurate positioning
- **Beautiful CLI**: Built with [typer](https://typer.tiangolo.com/) and [rich](https://rich.readthedocs.io/) for great terminal UX
- **Offline**: Everything runs locally, no cloud services needed
- **Extensible**: Easy to add new platform scanners via the abstract base class

## How It Works

WiFi fingerprinting works by:

1. **Learning phase**: You walk to each room/location and record the WiFi signals visible from there. Each location gets a unique "fingerprint" — the set of access points and their signal strengths (RSSI).
2. **Training phase**: A machine learning model learns the relationship between WiFi signal patterns and locations.
3. **Prediction phase**: When you want to know where you are, the system scans current WiFi signals and uses the trained model to predict your location.

The key insight is that WiFi signal strengths vary predictably based on your physical location relative to access points, due to walls, distance, and other obstacles.

## Installation

```bash
# Clone and install
cd wifi-positioning
pip install -e .

# For macOS Location Services support (macOS only)
pip install -e ".[macos]"

# For development (includes pytest)
pip install -e ".[dev]"
```

### Platform-Specific Notes

#### macOS

- On macOS 14+, WiFi scanning requires **Location Services** authorization.
- Go to **System Preferences > Privacy & Security > Location Services** and enable it for your terminal app (Terminal, iTerm2, etc.).
- wifipos uses the CoreWLAN framework (via pyobjc), not the deprecated `airport` command.

#### Linux

- Uses `nmcli` (NetworkManager) by default. Falls back to `iwlist` if nmcli is unavailable.
- Some systems may require `sudo` for WiFi scanning with `iwlist`.
- Ensure your user is in the `netdev` group: `sudo usermod -aG netdev $USER`

#### Windows

- Uses `netsh wlan show networks mode=bssid` to scan WiFi networks.
- Should work out of the box on Windows 10/11 with WiFi enabled.

## Quick Start

### 1. Learn locations

Walk to each room and run:

```bash
# Learn your office (collect 10 WiFi samples)
wifipos learn office --samples 10 --interval 2

# Move to the kitchen and learn it
wifipos learn kitchen --samples 10 --interval 2

# Learn as many locations as you want
wifipos learn bedroom --samples 10
```

### 2. Train the model

```bash
wifipos train
```

This trains a RandomForest classifier and reports cross-validation accuracy.

### 3. Predict your location

```bash
# Single prediction
wifipos predict

# Continuous tracking
wifipos track --interval 3
```

### Other Commands

```bash
# Show learned locations and fingerprint counts
wifipos locations

# Delete a location's data
wifipos forget office

# Show model status and accuracy
wifipos status

# Export fingerprints to CSV
wifipos export data.csv

# Reset all data
wifipos reset --confirm
```

## Supported Platforms

| Platform | Scanner Method | Notes |
|----------|---------------|-------|
| macOS    | CoreWLAN (pyobjc) | Requires Location Services on macOS 14+ |
| Linux    | nmcli / iwlist | nmcli preferred, iwlist as fallback |
| Windows  | netsh | Works out of the box |

## Troubleshooting

### macOS: "No networks found" or BSSID/SSID returns None

- Enable Location Services for your terminal app in **System Preferences > Privacy & Security > Location Services**.
- On macOS 14.4+, Apple restricts access to WiFi scan data without Location Services authorization.

### Linux: "Permission denied" or empty scan results

- Try running with `sudo`: `sudo wifipos learn office`
- Add your user to the netdev group: `sudo usermod -aG netdev $USER`
- Ensure NetworkManager is running: `systemctl status NetworkManager`

### Windows: "WiFi is turned off"

- Enable WiFi in **Settings > Network & Internet > Wi-Fi**.

### Low prediction accuracy

- Collect more samples per location (15-20 recommended).
- Ensure locations are physically distinct (different rooms, not just different spots in the same room).
- Retrain after collecting more data: `wifipos train`

## Project Structure

```
wifi-positioning/
├── pyproject.toml
├── README.md
├── src/
│   └── wifipos/
│       ├── __init__.py
│       ├── cli.py            # CLI interface (typer + rich)
│       ├── scanner/
│       │   ├── base.py       # Abstract base scanner + WifiReading
│       │   ├── macos.py      # macOS scanner (CoreWLAN)
│       │   ├── linux.py      # Linux scanner (nmcli / iwlist)
│       │   └── windows.py    # Windows scanner (netsh)
│       ├── model/
│       │   ├── fingerprint.py # Fingerprint collection & feature matrix
│       │   ├── trainer.py     # Model training with cross-validation
│       │   └── predictor.py   # Real-time prediction
│       ├── storage/
│       │   └── database.py    # SQLite storage
│       └── utils/
│           └── platform.py    # OS detection & scanner factory
├── tests/
│   ├── test_scanner.py
│   ├── test_model.py
│   └── test_storage.py
└── data/
```

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Make your changes and add tests
4. Run tests: `pytest`
5. Submit a pull request

### Adding a New Platform Scanner

To add support for a new platform:

1. Create a new file in `src/wifipos/scanner/` (e.g., `freebsd.py`)
2. Implement the `WifiScanner` abstract base class with a `scan()` method
3. Update `src/wifipos/utils/platform.py` to detect and return your scanner
4. Add tests in `tests/test_scanner.py`

## License

MIT
