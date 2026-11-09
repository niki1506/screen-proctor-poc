# Setup and Git sharing

ScreenProctor is a local Python application with a Streamlit browser interface
and a command-line interface. The current version is 0.4.4. Videos are processed
on the machine running the app; no cloud inference service or API key is required.

## Requirements

- Git, if cloning or publishing the project.
- Python 3.11–3.13; **Python 3.12 is recommended**. Check with `python3.12 --version`.
- Internet access for the initial Python dependency and model downloads.
- Disk space for the virtual environment, three model files, uploaded videos and reports.

Development and validation used macOS on Apple Silicon. Other operating systems
have not been validated. `requirements.lock` records that development environment;
packages with native code may require a separately resolved environment elsewhere.
A GPU is optional; CPU processing can take longer than the video's playback time.
PyAV wheels normally include the FFmpeg libraries needed for decoding.

## Set up from a Git clone on macOS or Linux

Replace the example URL with the actual repository URL. Use the name
`ScreenProctorPOC` as the local checkout directory:

```bash
git clone 'REPLACE_WITH_REPOSITORY_URL' ScreenProctorPOC
cd ScreenProctorPOC
bash setup.sh
bash run.sh
```

For your existing copy, start with `cd ~/Documents/ScreenProctorPOC` instead of
cloning. Keep that copy if it contains recordings or reports you need.

`setup.sh` creates `.venv`, installs the application and test dependencies using
`requirements.lock` as constraints, downloads YOLO11m, YOLO11n and YOLO11n-pose
into `models/`, writes their checksum manifest, and runs the automated tests.
RapidOCR assets come with the installed package. Wait for setup to finish
successfully before starting the app. There is no need to activate the virtual
environment when using these scripts.

`run.sh` starts Streamlit on the loopback interface. Open the URL printed in the
terminal, normally **http://localhost:8501**. If a port is already occupied,
Streamlit may use another port. To choose one explicitly:

```bash
.venv/bin/python -m streamlit run app.py --server.address 127.0.0.1 --server.port 8502
```

Leave the terminal running while using the app. Press **Ctrl+C** in that terminal
to stop it. Publishing the repository to Git does not deploy or host the app.

## Use the app

1. Upload a video and select the recording type: external camera, webcam, direct
   screen recording, or combined camera/screen panels.
2. For combined recordings, enter separate camera and screen regions. External
   camera mode automatically tries to locate the display; optional calibration
   is available under analysis settings.
3. Select **Analyze video** and wait for completion.
4. Review the screen-change comparisons, grouped observations and coverage gaps.
5. Select **Download PDF report with screenshots** for a readable, self-contained
   report. JSON remains available for technical processing.

Each analysis stores `report.pdf`, `report.json`, `review.html` and `evidence/`
under a new directory in `runs/`. Uploaded videos also remain under `runs/`.
Keep the original report and evidence directory together if you want to export
another PDF later. A downloaded JSON alone does not contain its screenshots.
The configured browser upload limit is 2,048 MB; long recordings may still require
substantial processing time and memory. Use the CLI when a browser upload is unsuitable.

## Manual setup and Windows

If you need to resolve dependencies independently of the macOS development lock,
these commands install the compatible ranges declared in `pyproject.toml`.
This creates a different environment: run the tests and validate representative
videos before relying on it.

macOS/Linux, from the project directory:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/python -m screenproctor.cli prepare-models --models models
.venv/bin/python -m pytest -q
.venv/bin/python -m streamlit run app.py --server.address 127.0.0.1
```

Windows PowerShell, with Python 3.12 installed:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[test]'
.\.venv\Scripts\python.exe -m screenproctor.cli prepare-models --models models
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1
```

The shell scripts are intended for macOS/Linux; the Windows commands are a
manual setup path and have not been tested on Windows.

## Run without the browser

From the project directory on macOS/Linux:

```bash
.venv/bin/screenproctor analyze \
  --input '/path/to/video.mp4' \
  --output runs/my-first-analysis \
  --mode external --fps 4
```

Use a new output directory for each run; existing results are preserved.
On Windows, use `.\.venv\Scripts\python.exe -m screenproctor.cli` in place of
`.venv/bin/screenproctor`.

Export an existing successful report to a new PDF filename:

```bash
.venv/bin/screenproctor export-pdf \
  --report '/path/to/original/run/report.json' \
  --output '/path/to/new-report.pdf'
```

If the JSON was downloaded elsewhere, add
`--evidence-root '/path/to/original/run'`, pointing to the directory containing
`evidence/`. Missing images are marked unavailable rather than invented.

Synthetic demo videos are generated locally and excluded from Git. To recreate
them after cloning:

```bash
.venv/bin/python tools/make_demo.py
.venv/bin/python tools/create_ai_demo.py
```

## Prepare this project for Git

Create a repository for **ScreenProctorPOC itself**, separate from other projects.
The `.gitignore` excludes the virtual environment, model weights, uploaded videos,
generated reports/evidence, local validation runs, backups, caches and common
local secrets files. Keep source code, tests, shell scripts, example JSON
configurations, `.streamlit/config.toml`, documentation, `pyproject.toml` and
`requirements.lock` in the repository.

For a first upload from a project directory that is not already a Git repository:

```bash
git init
git branch -M main
git add .
git diff --cached --name-only
```

Review the staged filenames before committing. `.gitignore` does not remove files
that were already tracked. Local validation reports and reference screenshots
are deliberately not included in a fresh clone; historical report links in the
validation notes therefore refer to local artifacts.

After reviewing the staged files, create the commit and connect your chosen
empty remote repository:

```bash
git commit -m 'Initial ScreenProctor POC'
git remote add origin 'REPLACE_WITH_REPOSITORY_URL'
git push -u origin main
```

Use your Git provider's normal authentication. No credentials belong in the
source code or repository URL. Third-party dependencies and models retain their
own licenses; see [THIRD_PARTY.md](THIRD_PARTY.md).

## Update an existing clone

Stop the app with Ctrl+C, preserve any local source changes, and then run:

```bash
git pull --ff-only
.venv/bin/python -m pip install -c requirements.lock -e '.[test]'
.venv/bin/python -m pytest -q
bash run.sh
```

These commands assume the validated macOS environment. If you used the manual
setup above, retain that environment's dependency strategy instead of applying
macOS constraints. Run `prepare-models` again if required model files change or
are missing. Existing videos and reports are preserved.

When detection logic changes, use **Analyze video** again to obtain new results.
Re-exporting an older PDF refreshes presentation only; it does not detect missed
events in the original video.

## Troubleshooting

| Symptom | Action |
|---|---|
| Python version check fails | Install Python 3.12 and recreate the virtual environment using that interpreter. |
| Dependency installation fails | Check Python version and package wheel availability for your OS; use the manual setup for a separately resolved environment. Do not bypass failed tests. |
| Models or checksum manifest missing | Run `.venv/bin/screenproctor prepare-models --models models` with internet access. |
| A model checksum differs | Preserve the existing file for investigation and reacquire the model from its trusted upstream source before analysis. |
| Browser URL does not open | Check that the terminal process is running and use the exact localhost URL and port it prints. |
| Port is already in use | Start Streamlit with an explicit available port, as shown above. |
| PDF images are missing | Export alongside the original `evidence/` directory, or supply `--evidence-root`. |
| Older results are still displayed | Run Analyze video again; changing the report format alone does not rerun detection. |

For recording modes, calibration and interpretation of results, see [README.md](README.md).
