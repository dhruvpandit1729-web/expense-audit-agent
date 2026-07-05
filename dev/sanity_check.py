from dotenv import load_dotenv
load_dotenv()

from google.adk.agents import Agent
from google.adk.runners import InMemoryRunner
from google.genai import types
import asyncio

test_agent = Agent(
    name="SanityCheck",
    model="gemini-2.5-flash",
    instruction="Reply with exactly: OK",
)

async def main():
    runner = InMemoryRunner(agent=test_agent, app_name="sanity")
    session = await runner.session_service.create_session(
        app_name="sanity", user_id="test_user", session_id="test_session"
    )
    msg = types.Content(role="user", parts=[types.Part(text="ping")])
    async for event in runner.run_async(user_id="test_user", session_id="test_session", new_message=msg):
        if event.is_final_response():
            print(event.content.parts[0].text)

asyncio.run(main())