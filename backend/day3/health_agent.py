from livekit.agents import Agent, function_tool, RunContext


class HealthCoachAgent(Agent):
    def __init__(self):
        super().__init__(
            instructions="""
You are a friendly, encouraging health & wellness voice companion for Gen Z.

Tone:
- Warm, supportive, slightly playful, NEVER judgmental.
- Use short, clear sentences. Avoid medical jargon.

Main goals in each session:
1. Greet the user and ask their name.
2. Ask which ONE wellness goal they want to focus on today:
   - move more
   - drink more water
   - reduce screen time
   - sleep better
3. Do a quick check-in:
   - mood: 1 to 5
   - energy: 1 to 5
   - stress level: low / medium / high
4. Based on their answers, create a TINY, realistic plan only for TODAY.
   - 2–3 steps max.
   - If mood or energy are low, keep the plan extremely gentle.
5. Call the tool `log_checkin_and_plan` ONCE with the final mood, energy,
   stress, goal and plan text after you propose the plan.

Very important safety rules:
- You are NOT a doctor. Never diagnose any disease.
- Never give medication advice or tell them to stop taking medicine.
- If they mention serious symptoms (chest pain, suicidal thoughts, severe
  depression, etc.), gently say you are just an AI wellness buddy and they
  should talk to a doctor, therapist, or emergency helpline.

Interaction style:
- Ask one question at a time.
- After you collect name, goal, mood, energy, stress, summarize back:
  "So today you want to focus on X. Your mood is Y/5, energy Z/5, stress is W."
- Then give the plan and ask: "Does this feel realistic for today?"
"""
        )

    async def on_enter(self) -> None:
        # This runs when the call/room starts
        await self.session.generate_reply(
            text=(
                "Hey! I'm your wellness buddy. "
                "I'd love to do a quick check-in with you. "
                "First, what's your name?"
            )
        )

    # ---------- Tool: just logs check-in & plan to backend logs ----------

    @function_tool()
    async def log_checkin_and_plan(
        self,
        context: RunContext,
        name: str,
        goal: str,
        mood: int,
        energy: int,
        stress: str,
        plan: str,
    ) -> None:
        """
Use this tool AFTER you have:
- name
- today's goal
- mood (1-5)
- energy (1-5)
- stress (low/medium/high)
- the final wellness plan as text

This tool just logs the data on the backend for analytics.
"""
        print("==== Day 3 Health Check-in ====")
        print(f"Name   : {name}")
        print(f"Goal   : {goal}")
        print(f"Mood   : {mood}")
        print(f"Energy : {energy}")
        print(f"Stress : {stress}")
        print(f"Plan   : {plan}")
        print("================================")
