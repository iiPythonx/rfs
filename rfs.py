# Copyright (c) 2024-2025 iiPython

__version__ = "0.2.0"

# Modules
import shlex
import shutil
from pathlib import Path

import click
import uvicorn
from fastapi import FastAPI, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from requests import Session
from requests_toolbelt import MultipartEncoder, MultipartEncoderMonitor

from rich.console import Console
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

# Initialization
console = Console()

# Handle CLI
@click.group(epilog = "Copyright (c) 2024-2025 iiPython")
def rfs() -> None:
    """iiPython's Remote FileSystem Implementation
    \b
    https://github.com/iiPythonx/rfs"""
    pass

@rfs.command("serve", help = "Serve a specific location over RFS")
@click.option("--host", default = "0.0.0.0", help = "Host to bind to")
@click.option("--port", default = 8000, type = int, help = "Port to bind to")
@click.argument("path", type = click.Path(file_okay = False, exists = True, path_type = Path))
def serve(host: str, port: int, path: Path) -> None:
    app = FastAPI(openapi_url = None)

    # Handle routing
    @app.get("/api/glob/{glob:path}")
    async def handle_glob(glob: str, ls: str = "no") -> JSONResponse:
        return JSONResponse({"code": 200, "data": [
            str(file.relative_to(path))
            for file in path.glob(glob) if (file.is_file() or ls == "yes")
        ]})

    @app.get("/api/download/{file_path:path}", response_model = None)
    async def handle_download(file_path: Path) -> JSONResponse | FileResponse:
        file_path = path / file_path
        if not (file_path.is_file() and file_path.relative_to(path)):
            return JSONResponse({"code": 404}, status_code = 404)

        return FileResponse(file_path, media_type = "application/octet-stream", filename = file_path.name)

    @app.post("/api/upload/{file_path:path}")
    async def handle_upload(file: UploadFile, file_path: Path) -> JSONResponse:
        file_path = path / file_path
        if not file_path.relative_to(path):
            return JSONResponse({"code": 403}, status_code = 403)

        file_path.parent.mkdir(parents = True, exist_ok = True)
        with file_path.open("wb") as handle:
            shutil.copyfileobj(file.file, handle)

        file.file.close()
        return JSONResponse({"code": 200})

    uvicorn.run(
        app,
        host = host,
        port = port
    )

@rfs.command("connect", help = "Connect to a remote host")
@click.argument("host")
def connect(host: str) -> None:
    url = f"{'http://' if '://' not in host else ''}{host.rstrip('/')}/api"

    # Create rich progress
    progress = Progress(
        TextColumn("[bold blue]{task.fields[filename]}"),
        BarColumn(bar_width = None),
        "[progress.percentage]{task.percentage:>3.1f}%",
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
    )

    session, block_size = Session(), 1024 ** 2
    while True:
        match shlex.split(console.input(f"[blue]\\[{url.split('://')[1].split(':')[0]}] [green]$ ")):
            case ["ls", *args]:
                response = session.get(f"{url}/glob/{args[0] if args else '.'}/*", params = {"ls": "yes"}).json()
                print(*response["data"])

            case ["download", glob, *args]:
                parent = Path(args[0]) if args else Path.cwd()
                if not parent.is_dir():
                    print("Specified output location does not exist as a valid directory.")
                    continue

                with console.status("Requesting file list..."):
                    response = session.get(f"{url}/glob/{glob}").json()["data"]
                    if not response:
                        response = session.get(f"{url}/glob/{glob}/**").json()["data"]

                progress.start()
                try:
                    for file in response:
                        file = parent / Path(file)
                        if file.exists():
                            continue

                        file.parent.mkdir(exist_ok = True, parents = True)

                        # Handle progress bar
                        response = session.get(f"{url}/download/{file.relative_to(parent)}", stream = True)
                        try:
                            task = progress.add_task("download", filename = file.name, total = int(response.headers.get("content-length", 0)))
                            with file.open("wb") as fh:
                                for data in response.iter_content(block_size):
                                    progress.update(task, advance = len(data))
                                    fh.write(data)

                        except PermissionError:
                            pass

                except KeyboardInterrupt:
                    print("Aborted!")

                progress.stop()

            case ["upload", *globs]:
                progress.start()

                def upload_file(path: Path, relative: str) -> None:
                    task = progress.add_task("download", filename = path.name, total = path.stat().st_size)
                    with path.open("rb") as fh:
                        e = MultipartEncoder(fields = {"file": ("filename", fh)})
                        m = MultipartEncoderMonitor(
                            e, lambda monitor: progress.update(task, completed = monitor.bytes_read)
                        )
                        session.post(f"{url}/upload/{relative}", data = m, headers = {"Content-Type": m.content_type})

                for glob in globs:
                    for item in Path().glob(glob):
                        if item.is_dir():
                            for file in item.rglob("*"):
                                if not file.is_file():
                                    continue

                                upload_file(file.absolute(), str(file))

                        else:
                            upload_file(item.absolute(), item.name)

                progress.stop()

            case ["help"]:
                console.print(f"\n\t[bold]iiPython RFS [blue]v{__version__}[/]\n\t    --> Connected to [yellow]{url}\n")
                console.print("\t[bold]Commands:[/] [magenta]help, ls, download, upload, exit\n")

            case ["exit"]:
                break

if __name__ == "__main__":
    rfs()
