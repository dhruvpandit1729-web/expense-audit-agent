from dotenv import load_dotenv
load_dotenv()

import asyncio
from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import InMemoryRunner
from google.genai import types


def add_numbers(a: float, b: float) -> float:
    """Add two numbers together."""
    return a + b


test_agent = Agent(
    name="OllamaSanityCheck",
    model=LiteLlm(model="ollama_chat/qwen2.5:7b"),
    instruction="You are a helpful assistant. Use the add_numbers tool when asked to add things.",
    tools=[add_numbers],
)


async def main():
    runner = InMemoryRunner(agent=test_agent, app_name="ollama_sanity")
    session = await runner.session_service.create_session(
        app_name="ollama_sanity", user_id="test_user", session_id="test_session"
    )
    msg = types.Content(role="user", parts=[types.Part(text="What is 47 plus 89? Use your tool.")])
    async for event in runner.run_async(user_id="test_user", session_id="test_session", new_message=msg):
        if event.is_final_response():
            print("FINAL RESPONSE:", event.content.parts[0].text)


asyncio.run(main())