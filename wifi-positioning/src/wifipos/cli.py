"""CLI interface for wifipos using typer and rich."""

from __future__ import annotations

import csv
import logging
import sys
from typing import Optional

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table

from wifipos.storage.database import Database

app = typer.Typer(
    name="wifipos",
    help="WiFi fingerprinting-based indoor positioning system.",
    add_completion=False,
)
console = Console()


def _setup_logging(verbose: bool) -> None:
    """Configure logging based on verbosity."""
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def _get_scanner():
    """Get the platform-appropriate WiFi scanner."""
    from wifipos.utils.platform import get_scanner

    try:
        return get_scanner()
    except RuntimeError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@app.command()
def learn(
    location: str = typer.Argument(..., help="Name of the location to learn"),
    samples: int = typer.Option(10, "--samples", "-s", help="Number of WiFi samples to collect"),
    interval: float = typer.Option(5.0, "--interval", "-i", help="Seconds between samples"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose output"),
) -> None:
    """Learn a location by collecting WiFi fingerprints."""
    _setup_logging(verbose)

    # On macOS the WiFi hardware needs ~5 s between scans to avoid
    # "Resource busy" errors.  Clamp the interval so users don't hit
    # this issue when passing a very small value.
    min_safe_interval = 5.0
    if interval < min_safe_interval:
        console.print(
            f"[yellow]Note:[/yellow] Interval raised to {min_safe_interval}s "
            f"(WiFi hardware needs time between scans)."
        )
        interval = min_safe_interval

    scanner = _get_scanner()
    db = Database()

    console.print(f"\n[bold blue]Learning location:[/bold blue] [green]{location}[/green]")
    console.print(f"Collecting {samples} samples with {interval}s interval...\n")

    from wifipos.model.fingerprint import collect_fingerprint

    collected = 0
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Collecting samples...", total=samples)

        def on_sample(idx: int, total: int, ap_count: int) -> None:
            nonlocal collected
            collected += 1
            progress.update(task, advance=1, description=f"Sample {idx + 1}/{total} ({ap_count} APs)")

        fingerprints = collect_fingerprint(
            scanner=scanner,
            location=location,
            num_samples=samples,
            interval=interval,
            callback=on_sample,
        )

    for fp in fingerprints:
        raw_data = [r.to_dict() for r in fp.readings]
        db.save_fingerprint(location, raw_data, fp.timestamp)

    console.print(f"\n[green]✓[/green] Saved {len(fingerprints)} fingerprints for '[bold]{location}[/bold]'")

    counts = db.get_fingerprint_count_by_location()
    total_locations = len(counts)
    total_fp = counts.get(location, 0)
    console.print(f"  Total locations: {total_locations}, Total fingerprints for '{location}': {total_fp}")

    min_recommended_fingerprints = 30
    if total_locations < 2:
        console.print(
            "\n[yellow]Tip:[/yellow] You need at least 2 locations before training. "
            "Run [bold]wifipos learn <another_location>[/bold] in a different spot."
        )
    elif total_fp < min_recommended_fingerprints:
        console.print(
            "\n[yellow]Tip:[/yellow] For better accuracy, collect from multiple "
            "positions within the room. Move to a different spot and run "
            f"[bold]wifipos learn {location}[/bold] again."
        )
    db.close()


@app.command()
def train(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose output"),
) -> None:
    """Train the positioning model using collected fingerprints."""
    _setup_logging(verbose)

    from wifipos.model.trainer import train_model

    db = Database()

    console.print("\n[bold blue]Training model...[/bold blue]\n")

    try:
        result = train_model(db)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        db.close()
        raise typer.Exit(1)

    # Display cross-validation results
    table = Table(title="Cross-Validation Results")
    table.add_column("Classifier", style="cyan")
    table.add_column("Accuracy", style="green", justify="right")

    for name, acc in sorted(result.comparison_results.items(), key=lambda x: -x[1]):
        marker = " ← selected" if name == result.classifier_name else ""
        table.add_row(name, f"{acc:.4f}{marker}")

    console.print(table)

    console.print(f"\n[green]✓[/green] Model trained successfully!")
    console.print(f"  Accuracy: [bold green]{result.accuracy:.4f}[/bold green]")
    console.print(f"  Locations: {', '.join(result.locations)}")
    console.print(f"  Features (BSSIDs): {result.feature_count}")
    console.print(f"  Samples: {result.sample_count}")
    console.print(f"  CV Scores: {[f'{s:.4f}' for s in result.cv_scores]}")
    db.close()


@app.command()
def predict(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose output"),
) -> None:
    """Predict current location (single prediction)."""
    _setup_logging(verbose)

    from wifipos.model.predictor import Predictor

    scanner = _get_scanner()
    db = Database()

    try:
        predictor = Predictor(db)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        db.close()
        raise typer.Exit(1)

    console.print("\n[bold blue]Scanning WiFi networks...[/bold blue]\n")

    prediction = predictor.predict(scanner)

    console.print(f"[bold green]📍 You are in: {prediction.location}[/bold green]")
    console.print(f"   Confidence: {prediction.confidence:.1%}\n")

    # Show probability bar chart
    table = Table(title="Location Probabilities")
    table.add_column("Location", style="cyan")
    table.add_column("Probability", style="green", justify="right")
    table.add_column("Bar", style="blue")

    for loc, prob in sorted(prediction.probabilities.items(), key=lambda x: -x[1]):
        bar = "█" * int(prob * 30)
        table.add_row(loc, f"{prob:.1%}", bar)

    console.print(table)
    db.close()


@app.command()
def track(
    interval: float = typer.Option(3.0, "--interval", "-i", help="Seconds between predictions"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose output"),
) -> None:
    """Predict continuously (real-time tracking)."""
    _setup_logging(verbose)

    from wifipos.model.predictor import Predictor

    scanner = _get_scanner()
    db = Database()

    try:
        predictor = Predictor(db)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        db.close()
        raise typer.Exit(1)

    console.print(f"\n[bold blue]Real-time tracking[/bold blue] (interval={interval}s)")
    console.print("Press [bold]Ctrl+C[/bold] to stop.\n")

    def on_prediction(prediction):
        console.print(
            f"📍 [bold green]{prediction.location}[/bold green] "
            f"({prediction.confidence:.1%})"
        )

    try:
        predictor.predict_continuous(scanner, interval=interval, callback=on_prediction)
    except KeyboardInterrupt:
        console.print("\n[yellow]Tracking stopped.[/yellow]")
    db.close()


@app.command()
def locations(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose output"),
) -> None:
    """Show all learned locations and fingerprint counts."""
    _setup_logging(verbose)

    db = Database()
    counts = db.get_fingerprint_count_by_location()

    if not counts:
        console.print("[yellow]No locations learned yet.[/yellow]")
        console.print("Run [bold]wifipos learn <location>[/bold] to get started.")
        db.close()
        return

    table = Table(title="Learned Locations")
    table.add_column("Location", style="cyan")
    table.add_column("Fingerprints", style="green", justify="right")

    for loc, count in sorted(counts.items()):
        table.add_row(loc, str(count))

    console.print(table)
    console.print(f"\nTotal: {len(counts)} locations, {sum(counts.values())} fingerprints")
    db.close()


@app.command()
def forget(
    location: str = typer.Argument(..., help="Name of the location to forget"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose output"),
) -> None:
    """Delete a location's data."""
    _setup_logging(verbose)

    db = Database()
    deleted = db.delete_location(location)

    if deleted == 0:
        console.print(f"[yellow]No fingerprints found for location '{location}'.[/yellow]")
    else:
        console.print(f"[green]✓[/green] Deleted {deleted} fingerprints for '[bold]{location}[/bold]'")
    db.close()


@app.command()
def status(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose output"),
) -> None:
    """Show model info (accuracy, locations, last trained)."""
    _setup_logging(verbose)

    db = Database()
    model = db.load_latest_model()

    if model is None:
        console.print("[yellow]No trained model found.[/yellow]")
        console.print("Run [bold]wifipos train[/bold] after collecting fingerprints.")
        db.close()
        return

    meta = model["metadata"]
    table = Table(title="Model Status")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Model ID", str(model["id"]))
    table.add_row("Created At", model["created_at"])
    table.add_row("Classifier", meta.get("classifier", "Unknown"))
    table.add_row("Accuracy", f"{meta.get('accuracy', 0):.4f}")
    table.add_row("Locations", ", ".join(meta.get("locations", [])))
    table.add_row("Features (BSSIDs)", str(meta.get("feature_count", 0)))
    table.add_row("Samples", str(meta.get("sample_count", 0)))

    console.print(table)

    if "comparison" in meta:
        comp_table = Table(title="Classifier Comparison")
        comp_table.add_column("Classifier", style="cyan")
        comp_table.add_column("CV Accuracy", style="green", justify="right")
        for name, acc in sorted(meta["comparison"].items(), key=lambda x: -x[1]):
            comp_table.add_row(name, f"{acc:.4f}")
        console.print(comp_table)

    db.close()


@app.command()
def export(
    output_file: str = typer.Argument(..., help="Output CSV file path"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose output"),
) -> None:
    """Export fingerprints to CSV."""
    _setup_logging(verbose)

    db = Database()
    fingerprints = db.get_all_fingerprints()

    if not fingerprints:
        console.print("[yellow]No fingerprints to export.[/yellow]")
        db.close()
        return

    # Collect all BSSIDs for column headers
    all_bssids: set[str] = set()
    for fp in fingerprints:
        for reading in fp["raw_data"]:
            if reading.get("bssid"):
                all_bssids.add(reading["bssid"])

    bssid_list = sorted(all_bssids)

    with open(output_file, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["location", "timestamp"] + bssid_list)

        for fp in fingerprints:
            rssi_map = {r["bssid"]: r["rssi"] for r in fp["raw_data"] if r.get("bssid")}
            row = [fp["location"], fp["timestamp"]]
            for bssid in bssid_list:
                row.append(rssi_map.get(bssid, -100))
            writer.writerow(row)

    console.print(f"[green]✓[/green] Exported {len(fingerprints)} fingerprints to [bold]{output_file}[/bold]")
    console.print(f"  Columns: location, timestamp, + {len(bssid_list)} BSSIDs")
    db.close()


@app.command()
def reset(
    confirm: bool = typer.Option(False, "--confirm", help="Confirm database reset"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose output"),
) -> None:
    """Reset all data (fingerprints and models)."""
    _setup_logging(verbose)

    if not confirm:
        console.print("[yellow]This will delete ALL fingerprints and models.[/yellow]")
        console.print("Run with [bold]--confirm[/bold] to proceed.")
        raise typer.Exit(0)

    db = Database()
    db.reset()
    console.print("[green]✓[/green] All data has been reset.")
    db.close()


@app.command()
def tips() -> None:
    """Show training tips for best positioning accuracy."""
    console.print("\n[bold blue]Training Tips for Best Accuracy[/bold blue]\n")

    console.print("[bold]1. Collect from multiple positions within each room[/bold]")
    console.print(
        "   WiFi signals vary even inside the same room. Run [bold]wifipos learn[/bold]"
    )
    console.print(
        "   several times from [green]different spots[/green] using the [bold]same location name[/bold]:"
    )
    console.print(
        '   [dim]$ wifipos learn kitchen --samples 10   # center of the room[/dim]'
    )
    console.print(
        '   [dim]$ wifipos learn kitchen --samples 10   # by the window[/dim]'
    )
    console.print(
        '   [dim]$ wifipos learn kitchen --samples 10   # near the door[/dim]'
    )
    console.print(
        "   Each run [green]adds[/green] fingerprints — it does not replace previous data.\n"
    )

    console.print("[bold]2. Recommended amounts[/bold]")
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Scenario")
    table.add_column("Samples/position", justify="right")
    table.add_column("Positions/room", justify="right")
    table.add_column("Total/room", justify="right")
    table.add_row("Quick test", "5", "1", "5")
    table.add_row("Normal use", "10", "3–4", "30–40")
    table.add_row("Best accuracy", "15–20", "4–5", "60–100")
    console.print(table)
    console.print()

    console.print("[bold]3. General tips[/bold]")
    console.print("   • More data = better accuracy. You can always add more later.")
    console.print("   • Rooms should be physically separated (walls help).")
    console.print("   • Run [bold]wifipos train[/bold] after adding new fingerprints.")
    console.print("   • Use [bold]wifipos locations[/bold] to check fingerprint counts.")
    console.print("   • Use [bold]wifipos status[/bold] to check model accuracy.")
    console.print()


if __name__ == "__main__":
    app()
