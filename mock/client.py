import argparse
import asyncio
import sys
from urllib.parse import quote
import websockets
from rich.console import Console

console = Console()


async def run(phone: str, name: str, port: int = 8000) -> None:
    encoded_phone = quote(phone, safe="")
    uri = f"ws://localhost:{port}/ws/{encoded_phone}"

    console.print(f"Connecting as [bold]{name}[/bold] ({phone})...")
    try:
        async with websockets.connect(uri) as ws:
            console.print("[green]Connected.[/green]")

            async def receive_loop():
                async for message in ws:
                    console.print(f"[cyan]{message}[/cyan]")

            async def send_loop():
                loop = asyncio.get_event_loop()
                while True:
                    line = await loop.run_in_executor(None, sys.stdin.readline)
                    if not line:
                        break
                    text = line.strip()
                    if text:
                        await ws.send(text)

            await asyncio.gather(receive_loop(), send_loop())
    except websockets.exceptions.ConnectionClosed:
        console.print("[yellow]Disconnected.[/yellow]")
    except OSError as e:
        console.print(f"[red]Connection failed: {e}[/red]")


def main():
    parser = argparse.ArgumentParser(description="Donna mock terminal client")
    parser.add_argument("--phone", required=True, help="Phone number (e.g. +15550000000)")
    parser.add_argument("--name", required=True, help="Display name")
    args = parser.parse_args()

    try:
        asyncio.run(run(args.phone, args.name))
    except KeyboardInterrupt:
        console.print("\n[yellow]Disconnected.[/yellow]")


if __name__ == "__main__":
    main()
