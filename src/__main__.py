"""Entry point Ð´Ð»Ñ Ð·Ð°Ð¿ÑƒÑÐºÐ° Ñ‡ÐµÑ€ÐµÐ· python -m src.

Ð—Ð°Ð¿ÑƒÑÐºÐ°ÐµÑ‚ uvicorn ÑÐµÑ€Ð²ÐµÑ€ Ñ FastAPI Ð¿Ñ€Ð¸Ð»Ð¾Ð¶ÐµÐ½Ð¸ÐµÐ¼.
Ð‘Ð¾Ñ‚ Ð·Ð°Ð¿ÑƒÑÐºÐ°ÐµÑ‚ÑÑ Ð°Ð²Ñ‚Ð¾Ð¼Ð°Ñ‚Ð¸Ñ‡ÐµÑÐºÐ¸ ÐºÐ°Ðº Ñ„Ð¾Ð½Ð¾Ð²Ð°Ñ Ð·Ð°Ð´Ð°Ñ‡Ð°.

Ð˜ÑÐ¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ð½Ð¸Ðµ:
    python -m src              # Production mode (Ð±ÐµÐ· hot-reload)
    python -m src --dev        # Development mode (Ñ hot-reload)
    python -m src --help       # ÐŸÐ¾ÐºÐ°Ð·Ð°Ñ‚ÑŒ ÑÐ¿Ñ€Ð°Ð²ÐºÑƒ
"""

import argparse

import uvicorn


def main() -> None:
    """Ð—Ð°Ð¿ÑƒÑÑ‚Ð¸Ñ‚ÑŒ Ð¿Ñ€Ð¸Ð»Ð¾Ð¶ÐµÐ½Ð¸Ðµ Ñ‡ÐµÑ€ÐµÐ· uvicorn."""
    parser = argparse.ArgumentParser(
        description="Klar â€” Telegram-Ð±Ð¾Ñ‚ Ð´Ð»Ñ AI-Ð³ÐµÐ½ÐµÑ€Ð°Ñ†Ð¸Ð¸ ÐºÐ¾Ð½Ñ‚ÐµÐ½Ñ‚Ð°",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
ÐŸÑ€Ð¸Ð¼ÐµÑ€Ñ‹:
    python -m src              # Production mode
    python -m src --dev        # Development mode Ñ hot-reload
    python -m src --port 3000  # Ð£ÐºÐ°Ð·Ð°Ñ‚ÑŒ ÐºÐ°ÑÑ‚Ð¾Ð¼Ð½Ñ‹Ð¹ Ð¿Ð¾Ñ€Ñ‚
        """,
    )
    parser.add_argument(
        "--dev",
        action="store_true",
        help="Ð’ÐºÐ»ÑŽÑ‡Ð¸Ñ‚ÑŒ hot-reload Ð´Ð»Ñ Ñ€Ð°Ð·Ñ€Ð°Ð±Ð¾Ñ‚ÐºÐ¸",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Ð¥Ð¾ÑÑ‚ Ð´Ð»Ñ ÑÐµÑ€Ð²ÐµÑ€Ð° (Ð¿Ð¾ ÑƒÐ¼Ð¾Ð»Ñ‡Ð°Ð½Ð¸ÑŽ: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="ÐŸÐ¾Ñ€Ñ‚ Ð´Ð»Ñ ÑÐµÑ€Ð²ÐµÑ€Ð° (Ð¿Ð¾ ÑƒÐ¼Ð¾Ð»Ñ‡Ð°Ð½Ð¸ÑŽ: 8000)",
    )
    args = parser.parse_args()

    if args.dev:
        # Development mode Ñ hot-reload
        uvicorn.run(
            "src.main:app",
            host=args.host,
            port=args.port,
            reload=True,
            reload_includes=["src/**/*.py"],
            reload_excludes=[".venv/**", "data/**", "tests/**", ".git/**"],
        )
    else:
        # Production mode Ð±ÐµÐ· hot-reload
        uvicorn.run(
            "src.main:app",
            host=args.host,
            port=args.port,
            reload=False,
        )


if __name__ == "__main__":
    main()



