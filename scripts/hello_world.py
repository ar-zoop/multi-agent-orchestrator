import os
from dotenv import load_dotenv
from anthropic import Anthropic
from openai import OpenAI

load_dotenv()


def call_anthropic_api(): 
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=100,
        messages=[
            {"role": "user", "content": "Say hello in one sentence."}
        ],
    )

    print("Claude says:", response.content[0].text)

def call_openai():
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "user", "content": "Say hello in one sentence."}
        ],
    )
    
    print("OpenAI says:", response.choices[0].message.content)
    print("Tokens used:", response.usage)
    
call_openai()