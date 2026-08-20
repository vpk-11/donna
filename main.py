"""
Donna's CLI entrypoint. One process, one command:

    python main.py --admin
        Starts the server and drops you into the admin's live terminal chat,
        in the same process. Reads ADMIN_PHONE/ADMIN_NAME from .env.

    python main.py --client-name NAME --client-phone PHONE
        Connects as a client to a server already running via --admin in
        another terminal. Deliberately lightweight — does not import the
        server, firewall, or orchestrator, so it starts instantly.

`uvicorn server:app` still works for anyone who wants the server alone.
"""
import argparse
import asyncio

# Load .env (if present) before config.py's Settings() reads it — needed in
# every mode, since ADMIN_PHONE/ADMIN_NAME are required fields regardless of
# whether this process ends up acting as admin or client.
from dotenv import load_dotenv
load_dotenv()

from config import settings


async def _wait_for_health(port: int, timeout: float = 30.0) -> None:
    import httpx
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    async with httpx.AsyncClient() as client:
        while loop.time() < deadline:
            try:
                r = await client.get(f"http://localhost:{port}/health", timeout=2.0)
                if r.status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            await asyncio.sleep(0.3)
    raise RuntimeError(f"Server did not become healthy within {timeout}s.")


async def _run_admin() -> None:
    import uvicorn
    from server import app  # heavy import (firewall, orchestrator, db) — admin mode only
    from mock.client import run as run_mock_client

    config = uvicorn.Config(app, host="0.0.0.0", port=settings.port, log_level="warning")
    server = uvicorn.Server(config)
    server_task = asyncio.create_task(server.serve())
    try:
        await _wait_for_health(settings.port)
        await run_mock_client(settings.admin_phone, settings.admin_name, port=settings.port)
    finally:
        server.should_exit = True
        await server_task


def _cli_main() -> None:
    parser = argparse.ArgumentParser(
        description="Donna — run the server as admin, or connect as a client."
    )
    parser.add_argument(
        "--admin", action="store_true",
        help="Start the server and connect as the admin (ADMIN_PHONE/ADMIN_NAME from .env).",
    )
    parser.add_argument("--client-name", help="Connect as a client with this display name.")
    parser.add_argument("--client-phone", help="Client's phone number, e.g. +15550001111.")
    args = parser.parse_args()

    if args.admin:
        if args.client_name or args.client_phone:
            parser.error("--admin can't be combined with --client-name/--client-phone.")
        asyncio.run(_run_admin())
        return

    if args.client_name or args.client_phone:
        if not (args.client_name and args.client_phone):
            parser.error("--client-name and --client-phone are required together.")
        from mock.client import run as run_mock_client
        try:
            asyncio.run(run_mock_client(args.client_phone, args.client_name, port=settings.port))
        except KeyboardInterrupt:
            pass
        return

    parser.error("Pass --admin, or --client-name NAME --client-phone PHONE.")


if __name__ == "__main__":
    _cli_main()
