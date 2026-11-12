"""Run Friday.

  python -m friday                 terminal mode (status screen, Enter to talk)
  python -m friday serve           engine for the desktop app (API + voice loop)
  python -m friday serve --no-voice    API only, no microphone
"""
import argparse
import os
import secrets


def main():
    parser = argparse.ArgumentParser(prog="friday", description="Friday voice assistant")
    sub = parser.add_subparsers(dest="mode")
    serve = sub.add_parser("serve", help="run the engine API for the desktop app")
    serve.add_argument("--port", type=int, default=int(os.environ.get("FRIDAY_PORT", "8765")))
    serve.add_argument("--no-voice", action="store_true", help="do not start the microphone loop")
    args = parser.parse_args()

    if args.mode == "serve":
        import uvicorn

        from friday.api.app import create_app

        # The desktop app passes FRIDAY_TOKEN. Started by hand, one is made and shown.
        token = os.environ.get("FRIDAY_TOKEN")
        if not token:
            token = secrets.token_urlsafe(24)
            print(f"Engine token (needed by clients): {token}")
        app = create_app(token=token, voice=not args.no_voice)
        uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
    else:
        from friday.app import main as terminal_main
        terminal_main()


if __name__ == "__main__":
    main()
