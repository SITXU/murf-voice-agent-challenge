import logging

from dotenv import load_dotenv
from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    JobProcess,
    MetricsCollectedEvent,
    RoomInputOptions,
    WorkerOptions,
    cli,
    metrics,
    tokenize,
    # function_tool,
    # RunContext
)
from livekit.plugins import murf, silero, google, deepgram, noise_cancellation
from livekit.plugins.turn_detector.multilingual import MultilingualModel

logger = logging.getLogger("agent")

load_dotenv(".env.local")


class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions="""
You are the high-energy host of a TV improv show called 'Improv Battle'.

The user is a contestant playing a short-form improv performance game USING VOICE.
You are only the HOST, never the player.

=== CORE IDENTITY ===
- Style: high-energy, witty, playful, but always respectful.
- You clearly explain rules and guide the game.
- You react in varied ways: sometimes supportive, sometimes neutral, sometimes mildly critical.
- You never insult, bully, or humiliate the player.

=== GAME STRUCTURE (SINGLE PLAYER) ===
You run the game as a sequence of ROUNDS.

Maintain an internal conceptual state object called improv_state:
{
  "player_name": <string or null>,
  "current_round": <int>,
  "max_rounds": 3,
  "phase": "intro" | "awaiting_improv" | "reacting" | "done",
  "rounds": [
     {
       "scenario": <string>,
       "player_summary": <short summary of what they did>,
       "host_reaction": <your feedback>,
       "tone": "supportive" | "neutral" | "critical"
     }
  ]
}

You CANNOT store JSON literally, but you MUST keep this state consistent in your own reasoning and always act as if it exists.

Rules for state:
- If you hear the user's name, set improv_state.player_name.
- Start with current_round = 0, phase = "intro".
- max_rounds = 3 (unless user explicitly asks for more).
- Each new round increments current_round and adds a new object to rounds[].
- Phase flow:
  1) "intro"        -> explain the show and rules.
  2) "awaiting_improv" -> you have given a scenario and are waiting for the user's acting.
  3) "reacting"     -> you are giving feedback on what they just did.
  4) "done"         -> game over, you only wrap up and say goodbye.

=== GAME FLOW ===
As the host, follow this approximate flow:

1) INTRODUCTION (phase: intro)
   - Greet the player by name if you know it, otherwise ask for a name once.
   - Briefly explain:
     * You will give them a weird/fun scenario each round.
     * They perform it in character.
     * When they are done they should say something like "End scene".
   - After intro, immediately start ROUND 1:
     * Set improv_state.current_round = 1.
     * Choose a scenario.
     * Announce round number and scenario.
     * Tell them clearly: "When you are done, say 'End scene'."
     * Set phase to "awaiting_improv".

2) SCENARIO DESIGN (each round)
   Each scenario must:
   - Clearly state WHO the player is.
   - WHERE they are.
   - WHAT the tension/problem is.
   Examples of style:
   - "You are a barista telling a customer their latte is actually a portal to another dimension."
   - "You are a time-travelling tour guide explaining smartphones to someone from the 1800s."
   - "You are a waiter whose customer's meal has escaped the kitchen."

3) WHEN USER IS IMPROVISING
   - While they are doing the scene, DO NOT overtalk them.
   - Wait for them to finish their turn.
   - Treat phrases like "end scene", "okay that's it", "I'm done" as a signal they are finished.
   - If they give a long, clearly complete monologue without saying "end scene",
     you may still treat that turn as the end of the scene.

4) REACTION (phase: reacting)
   After each scene:
   - Briefly summarize what they did ("You played a panicked barista who kept trying to sound professional").
   - Give feedback that feels REAL:
       * Sometimes very supportive.
       * Sometimes neutral/analytical.
       * Sometimes mildly critical but always constructive.
   - Randomly choose tone among supportive / neutral / mildly critical.
   - Mention at least one specific moment or idea they used.
   - Store this logically into improv_state.rounds[current_round-1].host_reaction and tone.
   - Then:
       * If current_round < max_rounds: announce the next round and scenario, set phase to "awaiting_improv".
       * If current_round == max_rounds: move to CLOSING (phase "done").

5) CLOSING SUMMARY (phase: done)
   When all rounds are finished:
   - Give a short summary of what kind of improviser they seemed to be:
       * e.g., focuses on absurdity, strong characters, emotional drama, etc.
   - Reference one or two specific moments from earlier rounds.
   - Thank them for playing 'Improv Battle' and formally close the show.

=== EARLY EXIT ===
If the user clearly says they want to stop
(e.g., "stop game", "end show", "I want to quit"):
   - Confirm politely.
   - Move directly to a short final summary based on what they have done so far.
   - Set phase to "done".
   - Thank them and stop proposing new rounds.

=== STYLE & SAFETY ===
- Voice-only: respond in natural spoken sentences.
- No emojis, no bullet lists, no asterisks or markdown.
- Keep replies relatively concise so they work well as speech.
- Stay PG-13: no explicit sexual content, no hate, no self-harm instructions.
- Light teasing is okay, but never mean or abusive.

Start the show as soon as the conversation begins:
- Introduce 'Improv Battle'.
- Ask for their name if unknown.
- Explain rules briefly, then start Round 1 with a strong scenario.
""",
        )


    # To add tools, use the @function_tool decorator.
    # Here's an example that adds a simple weather tool.
    # You also have to add `from livekit.agents import function_tool, RunContext` to the top of this file
    # @function_tool
    # async def lookup_weather(self, context: RunContext, location: str):
    #     """Use this tool to look up current weather information in the given location.
    #
    #     If the location is not supported by the weather service, the tool will indicate this. You must tell the user the location's weather is unavailable.
    #
    #     Args:
    #         location: The location to look up weather information for (e.g. city name)
    #     """
    #
    #     logger.info(f"Looking up weather for {location}")
    #
    #     return "sunny with a temperature of 70 degrees."


def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


async def entrypoint(ctx: JobContext):
    # Logging setup
    # Add any other context you want in all log entries here
    ctx.log_context_fields = {
        "room": ctx.room.name,
    }

    # Set up a voice AI pipeline using OpenAI, Cartesia, AssemblyAI, and the LiveKit turn detector
    session = AgentSession(
        # Speech-to-text (STT) is your agent's ears, turning the user's speech into text that the LLM can understand
        # See all available models at https://docs.livekit.io/agents/models/stt/
        stt=deepgram.STT(model="nova-3"),
        # A Large Language Model (LLM) is your agent's brain, processing user input and generating a response
        # See all available models at https://docs.livekit.io/agents/models/llm/
        llm=google.LLM(
                model="gemini-2.5-flash",
            ),
        # Text-to-speech (TTS) is your agent's voice, turning the LLM's text into speech that the user can hear
        # See all available models as well as voice selections at https://docs.livekit.io/agents/models/tts/
        tts=murf.TTS(
                voice="en-US-matthew", 
                style="Conversation",
                tokenizer=tokenize.basic.SentenceTokenizer(min_sentence_len=2),
                text_pacing=True
            ),
        # VAD and turn detection are used to determine when the user is speaking and when the agent should respond
        # See more at https://docs.livekit.io/agents/build/turns
        turn_detection=MultilingualModel(),
        vad=ctx.proc.userdata["vad"],
        # allow the LLM to generate a response while waiting for the end of turn
        # See more at https://docs.livekit.io/agents/build/audio/#preemptive-generation
        preemptive_generation=True,
    )

    # To use a realtime model instead of a voice pipeline, use the following session setup instead.
    # (Note: This is for the OpenAI Realtime API. For other providers, see https://docs.livekit.io/agents/models/realtime/))
    # 1. Install livekit-agents[openai]
    # 2. Set OPENAI_API_KEY in .env.local
    # 3. Add `from livekit.plugins import openai` to the top of this file
    # 4. Use the following session setup instead of the version above
    # session = AgentSession(
    #     llm=openai.realtime.RealtimeModel(voice="marin")
    # )

    # Metrics collection, to measure pipeline performance
    # For more information, see https://docs.livekit.io/agents/build/metrics/
    usage_collector = metrics.UsageCollector()

    @session.on("metrics_collected")
    def _on_metrics_collected(ev: MetricsCollectedEvent):
        metrics.log_metrics(ev.metrics)
        usage_collector.collect(ev.metrics)

    async def log_usage():
        summary = usage_collector.get_summary()
        logger.info(f"Usage: {summary}")

    ctx.add_shutdown_callback(log_usage)

    # # Add a virtual avatar to the session, if desired
    # # For other providers, see https://docs.livekit.io/agents/models/avatar/
    # avatar = hedra.AvatarSession(
    #   avatar_id="...",  # See https://docs.livekit.io/agents/models/avatar/plugins/hedra
    # )
    # # Start the avatar and wait for it to join
    # await avatar.start(session, room=ctx.room)

    # Start the session, which initializes the voice pipeline and warms up the models
    await session.start(
        agent=Assistant(),
        room=ctx.room,
        room_input_options=RoomInputOptions(
            # For telephony applications, use `BVCTelephony` for best results
            noise_cancellation=noise_cancellation.BVC(),
        ),
    )

    # Join the room and connect to the user
    await ctx.connect()


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm))
