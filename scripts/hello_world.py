import json
import os

from dotenv import load_dotenv
from anthropic import Anthropic
from google import genai
from openai import OpenAI

from anthropic_provider import AnthropicProvider
from chat_request import ChatRequest
from google_provider import GoogleProvider
from open_ai_provider import OpenAIProvider
from tool import Tool
from tool_registry import ToolRegistry

load_dotenv()


def get_weather(city: str) -> str:
    return f"In {city}, the weather is sunny today."

create_weather_tool = Tool(name = "get_weather", description = "Function to get the weather of a city", func = get_weather, 
                   parameters = {
					"type": "object",
					"properties": {"city": {"type": "string"}},
					"required": ["city"],
				},)

# def call_anthropic():
# 	client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
# 	Messages = [{"role": "user", "content": "Whats the weather in san francisco?"}]
# 	response = client.messages.create(
# 		model="claude-sonnet-4-6",
# 		max_tokens=100,
# 		messages=Messages
# 	)
# 	if response.stop_reason == "tool_use":
# 		func_to_call = TOOL_MAP.get(response.content[0].name)
# 		args = response.content[0].input
# 		res=func_to_call(**args)
# 		Messages.append({
# 			"role": "assistant",
# 			"content": [
# 				{
# 					"type": "tool_use",
# 					"id": response.content[0].id,
# 					"name": response.content[0].name,
# 					"input": response.content[0].input
# 				}
# 			]
# 		})
# 		Messages.append({
# 			"role": "user",
# 			"content": [
# 				{
# 					"type": "tool_result",
# 					"tool_use_id": response.content[0].id,
# 					"content": res
# 				}
# 			]
# 		})
# 		response = client.messages.create(
# 			model="claude-sonnet-4-6",
# 			max_tokens=100,
# 			messages=Messages
# 		)
# 		print(response.content[0].text)
# 	else :
# 		print(response.content[0].text)    


# def call_openai():
# 	client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
# 	messages = [{"role": "user", "content": "Whats the weather in New York City?"}]

# 	response = client.chat.completions.create(
# 		model="gpt-4o-mini",
# 		messages=messages,
# 		stream=False
# 	)

# 	tool_calls = response.choices[0].message.tool_calls
# 	if not tool_calls:
# 		print(response.choices[0].message.content)
# 		return

# 	tool_call = tool_calls[0]
# 	func_name = tool_call.function.name
# 	raw_arguments = tool_call.function.arguments
# 	arguments = json.loads(raw_arguments) if isinstance(raw_arguments, str) else raw_arguments

# 	func_to_call = TOOL_MAP.get(func_name)
# 	if func_to_call is None:
# 		raise ValueError(f"Unknown tool: {func_name}")

# 	result = func_to_call(**arguments)

# 	messages.append(response.choices[0].message)
	# messages.append(
	# 	{
	# 		"role": "tool",
	# 		"tool_call_id": tool_call.id,
	# 		"content": result,
	# 	}
	# )

# 	followup = client.chat.completions.create(
# 		model="gpt-4o-mini",
# 		messages=messages,
# 	)
# 	print(followup.choices[0].message.content)

# def call_gemini():
# 	client = genai.Client()

# 	interaction = client.interactions.create(
# 		model="gemini-3.5-flash",
# 		input="say hello world"
# 	)
# 	print(interaction)
# 	print(interaction.output_text)
	

def test():
    print("Starting the demo...\n")

    registry = {
        "openai": OpenAIProvider(),
        "anthropic": AnthropicProvider(),
        "google": GoogleProvider(),
    }

    provider_name = "google"
    provider = registry.get(provider_name)
    if provider is None:
        available = ", ".join(registry.keys())
        raise ValueError(f"Unknown provider: {provider_name}. Available: {available}")

    request = ChatRequest(
        model="gemini-3.5-flash",
        messages=["Please say hello in Hindi."],
        temperature=1.0,
    )
    response = provider.complete(request)
    print(f"{response.provider} says: {response.content}\n")

    tool_registry = ToolRegistry()
    tool_registry.register(create_weather_tool)

    weather_tool = tool_registry.get("get_weather")
    print(f"Weather tool output: {weather_tool.func('New York')}")

 
 
 
#-------------------
#  Google api response format - 
#  status='completed' 
# model='gemini-3.5-flash' 
# agent=None id='v1_ChdCdmRYYXZDTUZlWEZqdU1QeWVYTjBBYxIXQnZkWGF2Q01GZVhGanVNUHllWE4wQWM' 
# created='2026-07-15T21:09:26Z' 
# updated='2026-07-15T21:09:26Z' 
# system_instruction=None 
# tools=None 
# usage=Usage(cached_tokens_by_modality=None, grounding_tool_count=None, input_tokens_by_modality=[ModalityTokens(modality='text', tokens=4)], output_tokens_by_modality=None, tool_use_tokens_by_modality=None, total_cached_tokens=0, total_input_tokens=4, total_output_tokens=4, total_thought_tokens=81, total_tokens=89, total_tool_use_tokens=0) 
# response_modalities=None 
# response_mime_type=None 
# previous_interaction_id=None 
# environment_id=None 
# service_tier='standard' 
# webhook_config=None 
# steps=[ThoughtStep(signature='EpsDCpgDARFNMg8xyG54PUJ4/XcccpQ0Xk1TropAxNAv2r78z0WU9TBAusLYYY4vsDp7FCqM0Xk7Hhdt+8BDe1A5gnQSG9PT1b5okEcKuVTUZyEDKEiMh0YMs1UHV3Q/jkdVrnlVaUzdFqsRsv9HwmV6nQl/vxCWKPFH+ZYWkTKfEnwyAuuZqpD0Hp1WR0Egq/n8oZ4i/e1zkLPtkmqApbSgJRtAnLddP3+fqkQZlOX3LaD4IfAC83tJGOrZEehGhskte48tbjEitv5JuLR/VtWPPjcO2MC1JUHpqmGNS+B3IJ1Q09QFiiuvAby0xTPWphnahfhNM+M8HJANdPcdtYZbQP7MFgcZ0N+R5ApOAvzx1MBtAmVvJLyZSQHyZeLt411sQnS63mWAsL5D3w2aN5JPsuO5KZKCckT4iERVz8SBeDKjWgXZ+dN72KBAIvzBKbLfvoBEIfFnLGB5OyOicIPeN5S+Za9HQStTSF+ZjLoVGR1WTuetm0BhNibcdXi+KWIaDL8oNAfui87hWJ6pSYaoVheR/+XwVzbQJwti', summary=None, type='thought'), ModelOutputStep(content=[TextContent(text='Hello, World!', annotations=None, type='text')], error=None, type='model_output')] 
# response_format=None 
# environment=None 
# generation_config=None 
# cached_content=None 
# agent_config=None 
# safety_settings=None 
# labels=None 
# input=None 
# output_text='Hello, World!' 
# output_image=None 
# output_audio=None 
# output_video=None 
# object='interaction'
#--------------------