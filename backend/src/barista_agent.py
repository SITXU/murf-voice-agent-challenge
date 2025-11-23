from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional
from livekit.agents import Agent, RunContext, function_tool

# ------------ MENU ------------

COFFEE_MENU = {
    "latte": {"small": 180, "medium": 220, "large": 260},
    "cappuccino": {"small": 170, "medium": 210, "large": 250},
    "americano": {"small": 150, "medium": 190, "large": 230},
    "cold brew": {"small": 200, "medium": 240, "large": 280},
}

ADDONS = {
    "extra shot": 40,
    "vanilla syrup": 30,
    "caramel syrup": 30,
    "oat milk": 30,
    "almond milk": 30,
}

@dataclass
class OrderItem:
    drink: str
    size: str
    milk: Optional[str] = None
    addons: Optional[List[str]] = None

def price_item(item: OrderItem) -> int:
    base = COFFEE_MENU[item.drink][item.size]
    total = base + sum(ADDONS[a] for a in (item.addons or []) if a in ADDONS)
    return total

# ------------ AGENT ------------

BARISTA_PROMPT = """
You are Falcon Barista, a friendly AI coffee shop barista.
Speak naturally and guide the user through ordering coffee.
Steps:
1. Greet and ask their name.
2. Ask for drink type, size, milk, and addons.
3. Confirm final order.
4. THEN use the price_order tool.
5. After getting the result, tell the price and order ID.
Keep responses short and natural.
"""

class BaristaAgent(Agent):
    def __init__(self):
        super().__init__(instructions=BARISTA_PROMPT)

    @function_tool()
    async def get_menu(self, context: RunContext) -> Dict[str, Any]:
        return {"drinks": COFFEE_MENU, "addons": ADDONS, "currency": "INR"}

    @function_tool()
    async def price_order(
        self, context: RunContext, items: List[Dict[str, Any]]
    ) -> Dict[str, Any]:

        detailed = []
        total = 0

        for raw in items:
            item = OrderItem(
                drink=raw["drink"], size=raw["size"],
                milk=raw.get("milk"),
                addons=raw.get("addons", [])
            )
            price = price_item(item)
            total += price
            entry = asdict(item)
            entry["price"] = price
            detailed.append(entry)

        import random
        return {
            "items": detailed,
            "total": total,
            "order_id": f"CAF-{random.randint(100,999)}",
            "currency": "INR",
        }
