from __future__ import annotations

import argparse
import json

from .agent import DatabaseChatAgent
from .config import Settings
from .db import make_engine


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Gemma DB Chat Agent")
    parser.add_argument("command", choices=["analyze", "chat"], help="Operation mode")
    parser.add_argument("--db-uri", required=True, help="SQLAlchemy database URI")
    parser.add_argument(
        "--max-rows",
        type=int,
        default=None,
        help="Override MAX_RESULT_ROWS for generated query results",
    )
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    settings = Settings()
    if args.max_rows is not None:
        settings.max_result_rows = args.max_rows

    engine = make_engine(args.db_uri)
    agent = DatabaseChatAgent(engine, settings)

    if args.command == "analyze":
        print(json.dumps(agent.get_analysis(), indent=2, default=str))
        return

    print("Interactive DB chat started. Type 'exit' to quit.")
    while True:
        question = input("\nYou> ").strip()
        if not question:
            continue
        if question.lower() in {"exit", "quit"}:
            print("Bye.")
            break

        try:
            result = agent.ask(question)
            if result["sql"]:
                print(f"\nSQL> {result['sql']}")
                print(f"\nWhy this SQL> {result.get('explanation', 'N/A')}")
            print(f"\nAgent> {result['answer']}")
        except Exception as exc:
            print(f"\nError> {exc}")
