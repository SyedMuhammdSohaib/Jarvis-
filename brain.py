"""Jarvis ka dimagh: Claude + tools."""

import anthropic

from tools import ALL_TOOLS

MODEL = "claude-opus-5-5"

SYSTEM_PROMPT = """You are JARVIS, a personal AI assistant for your owner, Sohaib.
Personality: calm, witty, loyal, slightly formal - like Tony Stark's JARVIS. Call the user "Sir".
Reply in the same language the user writes in (English, Urdu or Roman Urdu).
Keep answers short and spoken-friendly (they may be read aloud later): no long lists or markdown tables.
Use your tools whenever they help. When the user tells you something about themselves
that is worth keeping (name, goals, preferences), save it with the `remember` tool.
At the start of a conversation, call `recall` if knowing the user would help."""


class Brain:
    def __init__(self):
        self.client = anthropic.Anthropic()  # ANTHROPIC_API_KEY env var se key leta hai
        self.messages = []  # poori conversation ki history

    def think(self, user_text: str) -> str:
        """User ka message lo, tools chalao agar zaroorat ho, aur final jawab do."""
        self.messages.append({"role": "user", "content": user_text})

        runner = self.client.beta.messages.tool_runner(
            model=MODEL,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            tools=ALL_TOOLS,
            messages=self.messages,
            output_config={"effort": "low"},  # chat ke liye fast jawab
            # Agar safety filter kabhi galti se mana kar de, to API khud dusre model pe retry karegi
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )

        last = None
        for message in runner:
            last = message
            # History khud sambhalte hain taake agla sawal pichli baat yaad rakhe
            self.messages.append({"role": "assistant", "content": message.content})
            tool_response = runner.generate_tool_call_response()
            if tool_response is not None:
                self.messages.append(tool_response)

        if last is None:
            return "Sorry Sir, kuch gadbad ho gayi."
        if last.stop_reason == "refusal":
            return "Maazrat Sir, main is mein madad nahi kar sakta."
        return "".join(block.text for block in last.content if block.type == "text").strip()
