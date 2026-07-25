import os

from provider import Provider
from openai import OpenAI
from chat_response import ChatResponse

class OpenAIProvider(Provider): 
    def complete(self, request):
        client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        response = client.chat.completions.create(
            model=request.model,
            messages=[{"role": "user", "content": s} for s in request.messages],
            temperature=request.temperature
        )
        chatResponse = ChatResponse(content= response.choices[0].message.content, provider= "openai", input_tokens=response.usage.prompt_tokens, output_tokens=response.usage.completion_tokens,)
        return chatResponse
