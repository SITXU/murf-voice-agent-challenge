# backend/day4/tutor_agent.py
"""
Day 4: Teach-the-Tutor LiveKit Agent (LiveKit Agents style).
Patterned after livekit-examples python-agents-examples/complex-agents/medical_office_triage/triage.py
but simplified and adapted for learn / quiz / teach_back modes.

Run with:
    uv run day4/main.py console
or
    uv run day4/main.py dev
"""

import os
import json
import uuid
import aiohttp
import asyncio
from difflib import SequenceMatcher
from typing import Optional, Dict, Any

# LiveKit Agents imports (match triage pattern)
from livekit.agents import Agent, AgentSession, JobContext, RunContext, WorkerOptions, cli, function_tool
from livekit.agents import utils as agents_utils  # if available in your version


ROOT = os.path.dirname(__file__)
CONTENT_PATH = os.path.join(ROOT, "day4_tutor_content.json")

# Load content
with open(CONTENT_PATH, "r", encoding="utf-8") as f:
    CONTENT = {c["id"]: c for c in json.load(f)}

VOICE_MAP = {"learn": "Matthew", "quiz": "Alicia", "teach_back": "Ken"}

# simple in-memory session store (agent sessions also have their own state)
SESSIONS: Dict[str, Dict[str, Any]] = {}

# env keys
MURF_API_KEY = os.getenv("MURF_API_KEY")
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")


# ----------------- Utilities -----------------
def _score_answer(reference: str, answer: str) -> float:
    if not answer or not reference:
        return 0.0
    return SequenceMatcher(None, reference.lower(), answer.lower()).ratio()


async def murf_tts_synthesize(text: str, voice: str = "Matthew") -> bytes:
    """
    Synthesizes text with Murf and returns raw audio bytes (e.g., mp3).
    Adapt payload/endpoint to your Murf account.
    If Murf returns a URL instead, return None and forward the URL instead.
    """
    if not MURF_API_KEY:
        raise RuntimeError("MURF_API_KEY not set")

    # Example Murf TTS endpoint (replace with correct one for your plan)
    endpoint = "https://api.murf.ai/v1/tts"

    payload = {"voice": voice, "text": text, "format": "mp3"}
    headers = {"Authorization": f"Bearer {MURF_API_KEY}", "Content-Type": "application/json"}

    async with aiohttp.ClientSession() as session:
        async with session.post(endpoint, json=payload, headers=headers, timeout=120) as resp:
            if resp.status not in (200, 201):
                body = await resp.text()
                raise RuntimeError(f"Murf TTS failed: {resp.status} {body}")

            # Many Murf endpoints either return a JSON with an audio_url or binary content.
            ct = resp.headers.get("Content-Type", "")
            if "application/json" in ct:
                j = await resp.json()
                # If JSON contains audio_url:
                audio_url = j.get("audio_url") or j.get("result", {}).get("audio_url")
                if audio_url:
                    return {"audio_url": audio_url}
                # Otherwise adapt here.
                raise RuntimeError("Murf returned JSON without audio_url; adapt code.")
            else:
                # binary audio
                data = await resp.read()
                return {"audio_bytes": data}


async def publish_audio_bytes_to_room(ctx: JobContext, audio_bytes: bytes, fmt: str = "mp3"):
    """
    Publish synthesized audio into the LiveKit room.
    The agents framework examples usually include helper utilities (publish_file or audio player).
    Here we use a common approach: save to temp file and call ctx.publish_local_audio or other helper.
    Adapt this to your environment (triage.py uses a helper to publish a file)
    """
    import tempfile
    import os

    tdir = tempfile.mkdtemp()
    fname = os.path.join(tdir, f"tts_{uuid.uuid4().hex}.{fmt}")
    with open(fname, "wb") as fh:
        fh.write(audio_bytes)

    # Many livekit examples provide `ctx.publish_audio_file` or `agents_utils.publish_audio_file`
    # Try to call a helper; otherwise, fallback to publishing via `ctx.room` helper.
    # If your triage.py had a helper, replace the call below with that helper.
    if hasattr(ctx, "publish_audio_file"):
        await ctx.publish_audio_file(fname)
    elif hasattr(agents_utils, "publish_audio_file"):
        await agents_utils.publish_audio_file(ctx, fname)
    else:
        # fallback: raise so you can plug your exact Triadge helper
        raise NotImplementedError("Please replace publish_audio_bytes_to_room implementation with the helper used in your project (see triage.py).")


async def transcribe_audio_bytes_via_deepgram(audio_bytes: bytes, mimetype: str = "audio/wav") -> str:
    """
    Transcribe raw audio bytes via Deepgram HTTP API and return transcript string.
    """
    if not DEEPGRAM_API_KEY:
        raise RuntimeError("DEEPGRAM_API_KEY not set")

    url = "https://api.deepgram.com/v1/listen?punctuate=true"
    headers = {"Authorization": f"Token {DEEPGRAM_API_KEY}", "Content-Type": mimetype}

    async with aiohttp.ClientSession() as session:
        async with session.post(url, data=audio_bytes, headers=headers, timeout=120) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise RuntimeError(f"Deepgram transcription failed: {resp.status} {body}")
            j = await resp.json()
    try:
        transcript = j["results"]["channels"][0]["alternatives"][0]["transcript"]
    except Exception:
        transcript = j.get("results", {}).get("channels", [{}])[0].get("alternatives", [{}])[0].get("transcript", "")
    return transcript or ""


# ----------------- Agent class -----------------
class TutorAgent(Agent):
    """
    An Agent subclass that implements the teach-the-tutor behavior.
    The Agent will:
      - greet the user
      - accept commands ('learn', 'quiz', 'teach back' + optional topic)
      - synthesize audio via Murf and publish into the room
      - record / capture user speech (via triage-like VAD/turn detection) and transcribe
      - score teach-back answers and respond with feedback
    """

    async def on_start(self, session: AgentSession, ctx: JobContext):
        """
        Called when a new AgentSession starts. Similar to triage.entrypoint.
        """
        # session.id (unique)
        sid = session.session_id or str(uuid.uuid4())
        SESSIONS[sid] = {"user_name": session.identity or "Learner", "mode": None, "history": []}
        # greet
        greeting = f"Hi {SESSIONS[sid]['user_name']}! Welcome to Teach-the-Tutor. Say 'learn', 'quiz', or 'teach back' followed by a topic."
        # synthesize
        tts = await murf_tts_synthesize(greeting, voice=VOICE_MAP["learn"])
        # tts returns dict with audio_bytes or audio_url
        if "audio_bytes" in tts:
            await publish_audio_bytes_to_room(ctx, tts["audio_bytes"])
        elif "audio_url" in tts:
            # optional: if Murf returned an audio URL, instruct frontend or use a helper to play in room
            await ctx.publish_audio_url(tts["audio_url"])  # may exist in some frameworks
        session.meta["day4_session_id"] = sid
        # Keep loop going -> listen for commands in entrypoint

    async def run(self, session: AgentSession, ctx: JobContext):
        """
        Primary loop. triage.py has logic to listen for user turns and run business logic.
        We'll implement a simplified loop: detect a command, act, and keep listening.
        """
        sid = session.meta.get("day4_session_id")
        if not sid:
            sid = str(uuid.uuid4())
            session.meta["day4_session_id"] = sid
            SESSIONS[sid] = {"user_name": session.identity or "Learner", "mode": None, "history": []}

        # Main listening loop: triage uses turn detector; we use agent utilities if available.
        # We'll use ctx.listen_for_turn() if present (triage uses similar helper)
        while True:
            try:
                # Wait for user to speak a command; triage uses a turn detector to capture utterance.
                if hasattr(ctx, "listen_for_turn"):
                    # The listen_for_turn helper usually returns bytes and transcript; adapt to your SDK.
                    rec = await ctx.listen_for_turn(timeout=60)
                    # rec could be a dict with 'transcript' or 'audio_bytes'
                    user_text = rec.get("transcript") if isinstance(rec, dict) else ""
                    audio_bytes = rec.get("audio_bytes") if isinstance(rec, dict) else None
                else:
                    # fallback: attempt to use ctx.receive_transcript() or ctx.receive_audio() if available.
                    if hasattr(ctx, "receive_transcript"):
                        user_text = await ctx.receive_transcript(timeout=60)
                        audio_bytes = None
                    else:
                        # If none of these exist, break and require you to plug in your triage helpers.
                        raise NotImplementedError("No turn-detection method available on ctx; please adapt run() to use your triage-like helper.")
            except asyncio.TimeoutError:
                # No activity; optionally end session
                break
            except Exception as e:
                # unexpected failure
                print("Error listening for user turn:", e)
                break

            if not user_text:
                # If we have audio bytes but no transcript, try to transcribe
                if audio_bytes:
                    try:
                        user_text = await transcribe_audio_bytes_via_deepgram(audio_bytes, mimetype="audio/wav")
                    except Exception as e:
                        user_text = ""
                if not user_text:
                    # nothing to process, keep listening
                    continue

            ut = user_text.strip().lower()
            # Recognize mode
            mode = None
            if "learn" in ut:
                mode = "learn"
            elif "quiz" in ut:
                mode = "quiz"
            elif "teach back" in ut or "teachback" in ut or "teach" in ut:
                mode = "teach_back"

            # Find concept if mentioned
            concept_id = None
            for cid, c in CONTENT.items():
                if c["title"].lower() in ut or cid in ut:
                    concept_id = cid
                    break

            if not mode:
                # No clear command, ask user to repeat
                help_text = "Say 'learn', 'quiz', or 'teach back' followed by the topic."
                tts = await murf_tts_synthesize(help_text, voice=VOICE_MAP["learn"])
                if "audio_bytes" in tts:
                    await publish_audio_bytes_to_room(ctx, tts["audio_bytes"])
                elif "audio_url" in tts:
                    await ctx.publish_audio_url(tts["audio_url"])
                continue

            # Execute selected mode
            await self._execute_mode(ctx, sid, mode, concept_id)

        # Clean up session on exit
        SESSIONS.pop(sid, None)
        return

    async def _execute_mode(self, ctx: JobContext, sid: str, mode: str, concept_id: Optional[str]):
        concept_id = concept_id or next(iter(CONTENT.keys()))
        concept = CONTENT.get(concept_id)
        if not concept:
            err = "Sorry, I don't know that topic."
            tts = await murf_tts_synthesize(err, voice=VOICE_MAP["learn"])
            if "audio_bytes" in tts:
                await publish_audio_bytes_to_room(ctx, tts["audio_bytes"])
            return

        if mode == "learn":
            text = concept["summary"]
            tts = await murf_tts_synthesize(text, voice=VOICE_MAP["learn"])
            if "audio_bytes" in tts:
                await publish_audio_bytes_to_room(ctx, tts["audio_bytes"])
            SESSIONS[sid]["history"].append({"type": "learn", "concept": concept_id})
            SESSIONS[sid]["current_concept"] = concept_id

        elif mode == "quiz":
            question = concept["sample_question"]
            tts = await murf_tts_synthesize(question, voice=VOICE_MAP["quiz"])
            if "audio_bytes" in tts:
                await publish_audio_bytes_to_room(ctx, tts["audio_bytes"])
            # Wait for user's spoken answer (use ctx.listen_for_turn if available)
            try:
                rec = await ctx.listen_for_turn(timeout=40)
                user_answer = rec.get("transcript") if isinstance(rec, dict) else ""
                audio_bytes = rec.get("audio_bytes") if isinstance(rec, dict) else None
                if not user_answer and audio_bytes:
                    user_answer = await transcribe_audio_bytes_via_deepgram(audio_bytes)
            except Exception:
                user_answer = ""
            reference = concept.get("summary", "") + " " + concept.get("sample_question", "")
            score = _score_answer(reference, user_answer)
            feedback = self._qualitative_feedback(score)
            feedback_text = f"Your score is {int(score*100)} percent. {feedback}"
            tts_fb = await murf_tts_synthesize(feedback_text, voice=VOICE_MAP["teach_back"])
            if "audio_bytes" in tts_fb:
                await publish_audio_bytes_to_room(ctx, tts_fb["audio_bytes"])
            SESSIONS[sid]["history"].append({"type": "answer", "record": {"concept": concept_id, "answer": user_answer, "score": score, "feedback": feedback}})

        elif mode == "teach_back":
            prompt = f"Please explain: {concept['title']}. {concept['sample_question']}"
            tts = await murf_tts_synthesize(prompt, voice=VOICE_MAP["teach_back"])
            if "audio_bytes" in tts:
                await publish_audio_bytes_to_room(ctx, tts["audio_bytes"])
            # Wait for teach-back answer
            try:
                rec = await ctx.listen_for_turn(timeout=50)
                user_answer = rec.get("transcript") if isinstance(rec, dict) else ""
                audio_bytes = rec.get("audio_bytes") if isinstance(rec, dict) else None
                if not user_answer and audio_bytes:
                    user_answer = await transcribe_audio_bytes_via_deepgram(audio_bytes)
            except Exception:
                user_answer = ""
            reference = concept.get("summary", "") + " " + concept.get("sample_question", "")
            score = _score_answer(reference, user_answer)
            feedback = self._qualitative_feedback(score)
            feedback_text = f"Nice attempt. Your score is {int(score*100)} percent. {feedback}"
            tts_fb = await murf_tts_synthesize(feedback_text, voice=VOICE_MAP["teach_back"])
            if "audio_bytes" in tts_fb:
                await publish_audio_bytes_to_room(ctx, tts_fb["audio_bytes"])
            SESSIONS[sid]["history"].append({"type": "answer", "record": {"concept": concept_id, "answer": user_answer, "score": score, "feedback": feedback}})

        else:
            raise ValueError("unknown mode")

    def _qualitative_feedback(self, score: float) -> str:
        if score > 0.7:
            return "Great — you covered most of the important points."
        elif score > 0.4:
            return "Good — you have the main idea, try to add more specific details."
        else:
            return "Keep trying — your explanation missed several key points. Review the summary and try again."


# ----------------- Entrypoint -----------------
async def entrypoint(ctx: JobContext):
    """
    This pattern mirrors triage.py: create an AgentSession, instantiate the Agent, and run it.
    The agents framework usually calls the Agent via WorkerOptions/cli helper.
    """
    # Create a TutorAgent instance and run it in the provided context/session
    agent = TutorAgent()
    # The exact way to start an agent session may vary with your livekit-agents version.
    # Use the pattern used in triage.py for your repo. Example:
    session = AgentSession(session_id=str(uuid.uuid4()), identity=getattr(ctx, "identity", "learner"))
    await agent.on_start(session, ctx)
    await agent.run(session, ctx)
    return

# If you prefer to mark a function tool (exposed to LLM as a tool), you can use @function_tool here.
