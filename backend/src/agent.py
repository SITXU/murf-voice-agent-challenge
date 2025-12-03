
import logging
import json
import os
from datetime import datetime
from typing import Dict, Any, Optional, List

import asyncio
from dotenv import load_dotenv

from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    JobProcess,
    RoomInputOptions,
    WorkerOptions,
    cli,
    tokenize,
    RunContext,
)
from livekit.plugins import murf, silero, google, deepgram, noise_cancellation
from livekit.plugins.turn_detector.multilingual import MultilingualModel

logger = logging.getLogger("improv_agent")
logging.basicConfig(level=logging.INFO)

load_dotenv(".env")

# ------------------------------------------------------------
# SYSTEM PROMPT (Improv Battle Host)
# ------------------------------------------------------------

def build_system_prompt() -> str:
    return """
You are the high-energy host of a TV improv game show called 'Improv Battle.'

Your personality:
- Energetic, witty, playful.
- You tease lightly, react honestly, and keep the vibe fun.
- You give real feedback: sometimes impressed, sometimes unimpressed, sometimes neutral.
- Always respectful.

Your job:
1. Introduce the show and explain the rules.
2. Run 3 improv rounds.
3. For each round:
   - Announce a scenario.
   - Ask the player to improvise in character.
   - Wait for them to finish or say 'end scene'.
   - React with a mix of praise + mild critique.
4. Give a final summary at the end.
5. If user says 'stop game', end session gracefully.

Reactions must feel varied: supportive, neutral, or lightly critical.
If you know the player's name, greet them personally.
"""


# ------------------------------------------------------------
# IMPROV AGENT (No E-commerce Code)
# ------------------------------------------------------------

class ImprovAgent(Agent):
    def __init__(self):
        super().__init__(instructions=build_system_prompt())
        self.improv_state = {
            "player_name": None,
            "current_round": 0,
            "max_rounds": 3,
            "phase": "intro",
            "rounds": []
        }

    # --------------------------
    # Read name from metadata
    # --------------------------
    async def on_participant_connected(self, participant):
        try:
            if participant.metadata:
                meta = json.loads(participant.metadata)
                self.improv_state["player_name"] = meta.get("playerName")
                logger.info(f"Player Joined: {self.improv_state['player_name']}")
        except Exception as e:
            logger.error(f"Metadata parse error: {e}")

    # -----------------------------------------------------
    # Inject player name into every LLM request
    # -----------------------------------------------------
    async def on_llm_request(self, ctx, messages):
        player_name = self.improv_state.get("player_name")

        if player_name:
            messages.insert(0, {
                "role": "system",
                "content": f"The player's name is {player_name}. Use it naturally whenever helpful."
            })

        return await super().on_llm_request(ctx, messages)

    # -----------------------------------------------------
    # (Optional) You can later add custom improv logic here
    # -----------------------------------------------------
    # on_user_turn_completed, on_exit, scenario selection, etc.


# ------------------------------------------------------------
# LIVEKIT RUNTIME SETUP
# ------------------------------------------------------------

def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


async def entrypoint(ctx: JobContext):
    print(">>> [BOOT] Improv Battle Agent starting...")

    vad = ctx.proc.userdata["vad"]

    session = AgentSession(
        stt=deepgram.STT(model="nova-3"),
        llm=google.LLM(model="gemini-2.5-flash"),
        tts=murf.TTS(
            voice="en-US-ken",
            style="Conversation",
            tokenizer=tokenize.basic.SentenceTokenizer(min_sentence_len=2),
            text_pacing=True,
        ),
        turn_detection=MultilingualModel(),
        vad=vad,
        preemptive_generation=True,
    )

    await ctx.connect()

    await session.start(
        agent=ImprovAgent(),
        room=ctx.room,
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVC(),
        ),
    )


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm
        )
    )
