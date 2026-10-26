"""JARVIS - Step 1: text chat. Chalane ke liye: python main.py"""

from dotenv import load_dotenv

load_dotenv()  # .env file se ANTHROPIC_API_KEY load karo

from brain import Brain  # noqa: E402


def main():
    jarvis = Brain()
    print("JARVIS online. Type 'exit' to quit.\n")
    while True:
        try:
            user_text = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not user_text:
            continue
        if user_text.lower() in ("exit", "quit", "bye"):
            break
        print(f"\nJARVIS: {jarvis.think(user_text)}\n")
    print("\nJARVIS: Goodbye, Sir.")


if __name__ == "__main__":
    main()
