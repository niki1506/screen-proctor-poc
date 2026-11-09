"""Command-line analysis and explicit one-time model preparation."""

import argparse
import hashlib
import json
import os
import sys
from dataclasses import fields
from pathlib import Path


def prepare(directory):
    directory = Path(directory).resolve()
    os.environ.setdefault(
        "YOLO_CONFIG_DIR", str(directory.parent / ".cache" / "ultralytics")
    )
    from ultralytics import YOLO, settings

    settings.update({"sync": False})

    directory.mkdir(parents=True, exist_ok=True)
    previous = Path.cwd()
    try:
        os.chdir(directory)
        for name in ("yolo11m.pt", "yolo11n.pt", "yolo11n-pose.pt"):
            YOLO(name)
        manifest = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in directory.glob("*.pt")
        }
        (directory / "checksums.json").write_text(json.dumps(manifest, indent=2) + "\n")
    finally:
        os.chdir(previous)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline proctoring event analysis")
    commands = parser.add_subparsers(dest="command", required=True)
    models = commands.add_parser("prepare-models")
    models.add_argument("--models", default="models")
    run = commands.add_parser("analyze")
    run.add_argument("--input", required=True, type=Path)
    run.add_argument(
        "--output",
        required=True,
        type=Path,
        help="A new directory; existing directories are preserved",
    )
    run.add_argument("--models", default="models", type=Path)
    run.add_argument("--config", type=Path, help="JSON configuration; see examples/")
    run.add_argument("--mode", choices=["external", "webcam", "screen", "combined"])
    run.add_argument("--fps", type=float)
    run.add_argument("--telemetry", type=Path)
    export = commands.add_parser(
        "export-pdf", help="Create a PDF from an existing report and local evidence"
    )
    export.add_argument("--report", required=True, type=Path)
    export.add_argument(
        "--output",
        required=True,
        type=Path,
        help="A new PDF filename; existing files are preserved",
    )
    export.add_argument(
        "--evidence-root",
        type=Path,
        help="Directory containing evidence/; defaults to the report directory",
    )
    args = parser.parse_args(argv)
    try:
        if args.command == "export-pdf":
            from .pdf_report import write_report_pdf

            report = json.loads(args.report.read_text())
            if report.get("status") != "success":
                raise ValueError("Only successful analysis reports can be exported")
            root = args.evidence_root or args.report.parent
            output = write_report_pdf(report, root, args.output)
            print(json.dumps({"pdf_report": str(output)}))
            return 0
        if args.command == "prepare-models":
            prepare(args.models)
            print(
                "Models prepared. Keep models/checksums.json with your evaluation records."
            )
            return 0
        from .analyzer import Config, analyze

        values = json.loads(args.config.read_text()) if args.config else {}
        allowed = {field.name for field in fields(Config)}
        if not isinstance(values, dict) or set(values) - allowed:
            raise ValueError("Configuration contains unknown fields")
        if args.mode is not None:
            values["mode"] = args.mode
        if args.fps is not None:
            values["fps"] = args.fps

        def progress(seconds, count):
            print(
                json.dumps(
                    {"processed_seconds": round(seconds, 2), "sample_count": count}
                ),
                flush=True,
            )

        report = analyze(
            args.input,
            args.output,
            args.models,
            Config(**values),
            progress,
            args.telemetry,
        )
        print(
            json.dumps(
                {
                    "report": str(args.output / "report.json"),
                    "pdf_report": str(args.output / "report.pdf"),
                    "events": len(report["events"]),
                }
            )
        )
        return 0
    except Exception as error:
        print(f"Analysis failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
