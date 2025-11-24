from dotenv import load_dotenv

# load env vars from .env.local and .env
load_dotenv(".env.local")
load_dotenv()

from livekit import agents
from livekit.agents import AgentSession
from health_agent import HealthCoachAgent


async def entrypoint(ctx: agents.JobContext):
    """
    This uses the default pipeline configured for the starter (STT + LLM + TTS),
    and only swaps the agent to our HealthCoachAgent.
    """
    # connect this job (room / console) to LiveKit
    await ctx.connect()

    # use the SAME STT/LLM/TTS that your starter already configures
    session = AgentSession()

    # start a session with our wellness agent
    await session.start(
        room=ctx.room,
        agent=HealthCoachAgent(),
    )


if __name__ == "__main__":
    agents.cli.run_app(
        agents.WorkerOptions(
            entrypoint_fnc=entrypoint,
        )
    )
