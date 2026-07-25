from provider import Provider
from google import genai
from chat_response import ChatResponse

class GoogleProvider(Provider):
    def complete(self, request):
        client = genai.Client()
        interaction = client.interactions.create(
            model= request.model,
            input= " ".join(request.messages)
        )
        chatResponse = ChatResponse(content = interaction.output_text, provider = "google", input_tokens = interaction.usage.total_input_tokens, output_tokens= interaction.usage.total_output_tokens)
        return chatResponse
