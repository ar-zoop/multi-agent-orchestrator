from openai import OpenAI
from dotenv import load_dotenv
from review_comment import ReviewComment
import os
import json

load_dotenv()


def call_structured_output():
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    response = client.beta.chat.completions.parse(
        messages = [{"role": "user", "content": "Please review this code that I found in a file. file main.py, line 42, someone wrapped a DB call in a bare except: pass"}],
        model = "gpt-4o-mini",
        response_format=ReviewComment
    )
    raw_response = response.choices[0].message.content
    print(type(raw_response))
    jsonresponse = json.loads(raw_response) if isinstance(raw_response, str) else raw_response
    print(type(jsonresponse))
    print(response.choices[0].message.parsed)
    print(response.choices[0].message.parsed.severity)


    

if __name__ == "__main__":
    call_structured_output()