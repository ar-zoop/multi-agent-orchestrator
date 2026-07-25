from provider import Provider
from anthropic import Anthropic
from chat_response import ChatResponse
import os

class AnthropicProvider(Provider):
    def complete(self, request):
        client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        Messages = [{"role": "user", "content": s} for s in request.messages]
        response = client.messages.create(
            model=request.model,
            max_tokens=100,
            messages=Messages,
            temperature=request.temperature
        )
        chatResponse = ChatResponse(content = response.content[0].text, provider = "anthropic", input_tokens = response.usage.input_tokens, output_tokens= response.usage.output_tokens)
        return chatResponse
