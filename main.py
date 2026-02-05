#!/usr/bin/env python3
"""
Multi-Model Opinion Flow - CLI
כלי לקבלת דעות מרובות ממודלים שונים
"""

import argparse
import asyncio
import sys
from pathlib import Path

from src.flow import run_flow, MultiModelFlow
from src.config import config, get_models_with_status


def print_banner():
    """הדפסת באנר"""
    print("""
╔══════════════════════════════════════════════════════════════╗
║           Multi-Model Opinion Flow                           ║
║           קבל דעות מרובות ממודלים מובילים                     ║
╚══════════════════════════════════════════════════════════════╝
""")


def list_models():
    """הצגת רשימת המודלים הזמינים"""
    print("\n📋 מודלים זמינים:\n")

    for model_id, name, available in get_models_with_status():
        status = "✅" if available else "❌"
        print(f"  {status} {model_id:12} - {name}")

    print("\n💡 הגדר API keys בקובץ .env או כמשתני סביבה")


async def interactive_mode():
    """מצב אינטראקטיבי"""
    print_banner()

    flow = MultiModelFlow()
    available = flow.get_available_models()

    if not available:
        print("❌ אין מודלים זמינים! הגדר API keys ב-.env")
        sys.exit(1)

    print(f"✅ מודלים זמינים: {', '.join(available)}\n")

    while True:
        print("-" * 60)
        question = input("\n📝 הכנס שאלה (או 'exit' ליציאה):\n> ").strip()

        if question.lower() in ['exit', 'quit', 'q', 'יציאה']:
            print("\n👋 להתראות!")
            break

        if not question:
            continue

        print(f"\n🚀 שולח ל-{len(available)} מודלים...\n")

        result = await run_flow(question, verbose=True)

        print("\n" + "=" * 60)
        print(result.final_summary)
        print("=" * 60)


async def run_single_question(question: str, models: list[str] = None, output_file: str = None):
    """הרצת שאלה בודדת"""
    result = await run_flow(question, models=models, verbose=True)

    if output_file:
        # שמירה לקובץ
        Path(output_file).write_text(result.final_summary, encoding="utf-8")
        print(f"\n💾 נשמר ל: {output_file}")
    else:
        # הדפסה למסך
        print("\n" + "=" * 60)
        print(result.final_summary)


def main():
    """נקודת כניסה ראשית"""
    parser = argparse.ArgumentParser(
        description="Multi-Model Opinion Flow - קבל דעות מרובות ממודלים",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
דוגמאות שימוש:
  python main.py                           # מצב אינטראקטיבי
  python main.py -q "מה זה Python?"        # שאלה בודדת
  python main.py -q "שאלה" -m claude gpt   # מודלים ספציפיים
  python main.py -q "שאלה" -o output.md    # שמירה לקובץ
  python main.py --list                    # רשימת מודלים
        """
    )

    parser.add_argument(
        "-q", "--question",
        type=str,
        help="השאלה לשליחה למודלים"
    )

    parser.add_argument(
        "-m", "--models",
        nargs="+",
        help="רשימת מודלים לשימוש (לדוגמה: claude gpt gemini)"
    )

    parser.add_argument(
        "-o", "--output",
        type=str,
        help="קובץ פלט לשמירת התוצאות (Markdown)"
    )

    parser.add_argument(
        "--list",
        action="store_true",
        help="הצג רשימת מודלים זמינים"
    )

    args = parser.parse_args()

    # הצגת רשימת מודלים
    if args.list:
        list_models()
        return

    # הרצת שאלה בודדת
    if args.question:
        asyncio.run(run_single_question(
            question=args.question,
            models=args.models,
            output_file=args.output
        ))
        return

    # מצב אינטראקטיבי
    asyncio.run(interactive_mode())


if __name__ == "__main__":
    main()
