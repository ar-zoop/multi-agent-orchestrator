import os

from dotenv import load_dotenv
from anthropic import Anthropic
from openai import OpenAI

load_dotenv()


def call_anthropic():
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    Messages = [{"role": "user", "content": "Say hello world "}]
    response = client.messages.stream(
        model="claude-sonnet-4-6",
        max_tokens=100,
        messages=Messages,
    )
    return response


def call_openai():
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    messages = [{"role": "user", "content": "Say hello world "}]

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        stream=True
    )
    return response


if __name__=="__main__":

    response = call_anthropic()
    with response as stream:
        for chunk in stream:
            if chunk.type=="content_block_delta":
                print(chunk.delta.text, end = "")
