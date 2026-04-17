"""
Microsoft Teams bot — wraps the FastAPI backend using Bot Framework SDK.
No retrieval or generation logic lives here; this is a thin transport layer.

Deploy alongside the FastAPI app. Teams sends activity events to /api/messages,
the bot calls the internal FastAPI /chat endpoint, and returns the response.

Setup:
  1. Register an Azure Bot resource in your tenant
  2. Set TEAMS_APP_ID and TEAMS_APP_PASSWORD in .env
  3. Configure the bot endpoint: https://<your-domain>/api/messages
"""
from __future__ import annotations

import os
import httpx
import uuid

from aiohttp import web
from botbuilder.core import (
    BotFrameworkAdapterSettings,
    BotFrameworkAdapter,
    TurnContext,
    ActivityHandler,
    MessageFactory,
)
from botbuilder.schema import Activity

TEAMS_APP_ID = os.getenv("TEAMS_APP_ID", "")
TEAMS_APP_PASSWORD = os.getenv("TEAMS_APP_PASSWORD", "")
API_BASE = os.getenv("API_BASE_URL", "http://localhost:8000")

SETTINGS = BotFrameworkAdapterSettings(TEAMS_APP_ID, TEAMS_APP_PASSWORD)
ADAPTER = BotFrameworkAdapter(SETTINGS)


class ITBot(ActivityHandler):
    async def on_message_activity(self, turn_context: TurnContext) -> None:
        query = (turn_context.activity.text or "").strip()
        if not query:
            await turn_context.send_activity(
                MessageFactory.text("Please ask me an IT question.")
            )
            return

        user_id = turn_context.activity.from_property.id or str(uuid.uuid4())

        async with httpx.AsyncClient(timeout=60) as client:
            try:
                resp = await client.post(
                    f"{API_BASE}/chat",
                    json={"query": query, "user_id": user_id},
                )
                resp.raise_for_status()
                data = resp.json()
            except httpx.HTTPError as exc:
                await turn_context.send_activity(
                    MessageFactory.text(f"Sorry, the knowledge base is unavailable: {exc}")
                )
                return

        answer = data.get("answer", "")
        citations = data.get("citations", [])
        disclaimer = data.get("disclaimer", "")
        ticket_draft = data.get("ticket_draft")

        # Build Teams-friendly markdown reply
        lines = [answer, ""]

        if citations:
            lines.append("**Sources:**")
            for cit in citations:
                title = cit.get("document_title", "Unknown")
                url = cit.get("source_url", "")
                if url:
                    lines.append(f"- [{title}]({url})")
                else:
                    lines.append(f"- {title}")
            lines.append("")

        if disclaimer:
            lines.append(f"> ⚠️ {disclaimer}")
            lines.append("")

        if ticket_draft:
            lines.append(
                "> 🎫 Low confidence — please open a support ticket if this answer doesn't help."
            )
            lines.append(f"> Suggested subject: *{ticket_draft.get('subject', '')}*")

        reply = "\n".join(lines)
        await turn_context.send_activity(MessageFactory.text(reply))


BOT = ITBot()


async def messages(req: web.Request) -> web.Response:
    if req.headers.get("Content-Type") != "application/json":
        return web.Response(status=415)

    body = await req.json()
    activity = Activity().deserialize(body)
    auth_header = req.headers.get("Authorization", "")

    response = await ADAPTER.process_activity(activity, auth_header, BOT.on_turn)
    if response:
        return web.json_response(data=response.body, status=response.status)
    return web.Response(status=201)


app = web.Application()
app.router.add_post("/api/messages", messages)

if __name__ == "__main__":
    web.run_app(app, host="0.0.0.0", port=3978)
