#!/usr/bin/env python3
"""save_model.py — CLI to save, restore and inspect WiFi positioning models.

Standalone script that works directly with the wifipos SQLite database
without needing the FastAPI server running.

Usage:
    python save_model.py save                     # Save model + fingerprints to .wifipos file
    python save_model.py save --output mi_casa    # Save with custom name
    python save_model.py load backup.wifipos      # Load model from file
    python save_model.py info                     # Show current DB status
    python save_model.py list                     # List saved .wifipos backups

The .wifipos file is a JSON bundle containing:
  - All WiFi fingerprints (location, timestamp, raw RSSI readings)
  - The trained ML model (base64-encoded sklearn pipeline)
  - Model metadata (accuracy, classifier, locations)
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Resolve database path (same as WiFiIntegrationService)
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).resolve().parent
_DATA_DIR = _SCRIPT_DIR / "data"
_DEFAULT_DB_PATH = _DATA_DIR / "wifipos.db"
_BACKUPS_DIR = _DATA_DIR / "backups"


def _get_db():
    """Open the wifipos SQLite database."""
    try:
        from wifipos.storage.database import Database
    except ImportError:
        print("❌ No se pudo importar wifipos. Ejecuta:")
        print("   cd local-server && pip install -r requirements.txt")
        sys.exit(1)

    if not _DEFAULT_DB_PATH.exists():
        print(f"⚠️  Base de datos no encontrada en {_DEFAULT_DB_PATH}")
        print("   Registra al menos un espacio primero desde la app.")
        sys.exit(1)

    return Database(str(_DEFAULT_DB_PATH))


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_save(args):
    """Export fingerprints + trained model to a .wifipos JSON file."""
    db = _get_db()

    fingerprints = db.get_all_fingerprints()
    model_row = db.load_latest_model()
    locations = db.get_locations()
    counts = db.get_fingerprint_count_by_location()

    if not fingerprints:
        print("⚠️  No hay fingerprints en la base de datos.")
        print("   Registra espacios desde la app primero.")
        db.close()
        return

    # Build bundle
    model_b64 = None
    model_meta = None
    if model_row is not None:
        model_b64 = base64.b64encode(model_row["model_blob"]).decode("ascii")
        model_meta = model_row["metadata"]

    bundle = {
        "version": 1,
        "exported_at": datetime.now().isoformat(),
        "fingerprints": fingerprints,
        "model_blob_b64": model_b64,
        "model_metadata": model_meta,
    }

    # Determine output path
    _BACKUPS_DIR.mkdir(parents=True, exist_ok=True)

    if args.output:
        name = args.output if args.output.endswith(".wifipos") else f"{args.output}.wifipos"
        out_path = _BACKUPS_DIR / name
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = _BACKUPS_DIR / f"modelo_{ts}.wifipos"

    out_path.write_text(json.dumps(bundle, indent=2, ensure_ascii=False), encoding="utf-8")

    db.close()

    # Summary
    print(f"✅ Modelo guardado en: {out_path}")
    print(f"   📍 Ubicaciones: {', '.join(locations)} ({len(locations)} total)")
    print(f"   🔢 Fingerprints: {sum(counts.values())}")
    for loc, count in counts.items():
        print(f"      • {loc}: {count}")
    if model_meta:
        acc = model_meta.get("accuracy", "?")
        clf = model_meta.get("classifier_name", model_meta.get("classifier", "?"))
        print(f"   🤖 Modelo: {clf} (accuracy: {acc})")
    else:
        print("   ⚠️  No hay modelo entrenado (solo fingerprints guardados)")
    print(f"\n   Para restaurar: python save_model.py load {out_path.name}")


def cmd_load(args):
    """Import a .wifipos bundle, replacing current DB data."""
    file_path = Path(args.file)

    # Also check in backups dir if file not found directly
    if not file_path.exists():
        alt = _BACKUPS_DIR / file_path.name
        if alt.exists():
            file_path = alt
        else:
            print(f"❌ Archivo no encontrado: {file_path}")
            sys.exit(1)

    try:
        bundle = json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"❌ Archivo JSON inválido: {exc}")
        sys.exit(1)

    # Validate bundle
    if "fingerprints" not in bundle:
        print("❌ El archivo no parece ser un bundle .wifipos válido (falta 'fingerprints')")
        sys.exit(1)

    fp_count = len(bundle.get("fingerprints", []))
    has_model = bool(bundle.get("model_blob_b64"))
    exported_at = bundle.get("exported_at", "?")

    print(f"📦 Bundle: {file_path.name}")
    print(f"   Exportado: {exported_at}")
    print(f"   Fingerprints: {fp_count}")
    print(f"   Modelo incluido: {'Sí' if has_model else 'No'}")

    if not args.yes:
        resp = input("\n⚠️  Esto REEMPLAZARÁ todos los datos actuales. ¿Continuar? [s/N] ")
        if resp.lower() not in ("s", "si", "sí", "y", "yes"):
            print("Cancelado.")
            return

    db = _get_db()

    # 1. Reset
    db.reset()

    # 2. Restore fingerprints
    restored_fps = 0
    for fp in bundle.get("fingerprints", []):
        ts = datetime.fromisoformat(fp["timestamp"]) if fp.get("timestamp") else datetime.now()
        db.save_fingerprint(fp["location"], fp["raw_data"], ts)
        restored_fps += 1

    # 3. Restore model
    model_restored = False
    if bundle.get("model_blob_b64"):
        model_bytes = base64.b64decode(bundle["model_blob_b64"])
        meta = bundle.get("model_metadata", {})
        db.save_model(model_bytes, meta)
        model_restored = True

    db.close()

    print(f"\n✅ Datos restaurados exitosamente:")
    print(f"   🔢 Fingerprints importados: {restored_fps}")
    print(f"   🤖 Modelo restaurado: {'Sí' if model_restored else 'No'}")
    print(f"\n   El servidor usará estos datos automáticamente al siguiente request.")


def cmd_info(args):
    """Show current database status."""
    db = _get_db()

    counts = db.get_fingerprint_count_by_location()
    locations = db.get_locations()
    model_row = db.load_latest_model()
    total_fps = sum(counts.values())

    print("📊 Estado actual del modelo WiFi")
    print(f"   Base de datos: {_DEFAULT_DB_PATH}")
    print(f"   Ubicaciones: {len(locations)}")
    print(f"   Fingerprints totales: {total_fps}")

    if counts:
        print("\n   Fingerprints por ubicación:")
        for loc, count in sorted(counts.items()):
            bar = "█" * min(count, 30)
            print(f"      {loc:20s} {count:4d}  {bar}")

    if model_row:
        meta = model_row.get("metadata", {})
        acc = meta.get("accuracy", "?")
        clf = meta.get("classifier_name", meta.get("classifier", "?"))
        created = model_row.get("created_at", "?")
        locs = meta.get("locations", [])
        print(f"\n   🤖 Modelo entrenado:")
        print(f"      Clasificador: {clf}")
        print(f"      Accuracy: {acc}")
        print(f"      Ubicaciones: {', '.join(str(l) for l in locs)}")
        print(f"      Creado: {created}")
    else:
        print("\n   ⚠️  No hay modelo entrenado")
        if len(locations) < 2:
            print(f"      Necesitas ≥2 ubicaciones (tienes {len(locations)})")
        else:
            need_more = [loc for loc, c in counts.items() if c < 3]
            if need_more:
                print(f"      Ubicaciones con <3 fingerprints: {', '.join(need_more)}")

    db.close()


def cmd_list(args):
    """List all saved .wifipos backups."""
    if not _BACKUPS_DIR.exists():
        print("📁 No hay backups guardados todavía.")
        print(f"   Directorio: {_BACKUPS_DIR}")
        print(f"   Usa: python save_model.py save")
        return

    files = sorted(_BACKUPS_DIR.glob("*.wifipos"), key=lambda f: f.stat().st_mtime, reverse=True)

    if not files:
        print("📁 No hay backups guardados todavía.")
        print(f"   Usa: python save_model.py save")
        return

    print(f"📁 Backups guardados ({len(files)}):")
    print(f"   Directorio: {_BACKUPS_DIR}\n")

    for f in files:
        size_kb = f.stat().st_size / 1024
        try:
            bundle = json.loads(f.read_text(encoding="utf-8"))
            fp_count = len(bundle.get("fingerprints", []))
            has_model = "✓ modelo" if bundle.get("model_blob_b64") else "sin modelo"
            exported = bundle.get("exported_at", "?")[:19]
        except Exception:
            fp_count = "?"
            has_model = "?"
            exported = "?"

        print(f"   {f.name:40s}  {size_kb:7.1f} KB  {fp_count} fps  {has_model}  ({exported})")

    print(f"\n   Para restaurar: python save_model.py load <archivo>")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Guardar y restaurar modelos de posicionamiento WiFi",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python save_model.py save                     Guardar modelo actual
  python save_model.py save --output mi_casa    Guardar con nombre personalizado
  python save_model.py load modelo.wifipos      Restaurar desde archivo
  python save_model.py info                     Ver estado actual del modelo
  python save_model.py list                     Listar backups guardados
        """,
    )
    sub = parser.add_subparsers(dest="command", help="Comando a ejecutar")

    # save
    p_save = sub.add_parser("save", help="Guardar modelo + fingerprints a archivo .wifipos")
    p_save.add_argument("--output", "-o", help="Nombre del archivo de salida (sin extensión)")

    # load
    p_load = sub.add_parser("load", help="Restaurar modelo desde archivo .wifipos")
    p_load.add_argument("file", help="Ruta al archivo .wifipos")
    p_load.add_argument("--yes", "-y", action="store_true", help="No pedir confirmación")

    # info
    sub.add_parser("info", help="Ver estado actual de la base de datos")

    # list
    sub.add_parser("list", help="Listar backups guardados")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    commands = {
        "save": cmd_save,
        "load": cmd_load,
        "info": cmd_info,
        "list": cmd_list,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
