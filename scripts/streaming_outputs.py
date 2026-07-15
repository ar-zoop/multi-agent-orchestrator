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
    # response = call_openai()
    # for chunk in response:
    #     if chunk.choices[0].delta.content :
    #         print(chunk.choices[0].delta.content, end = "", flush=True)
    
    response = call_anthropic()
    with response as stream:
        for chunk in stream:
            if chunk.type=="content_block_delta":
                print(chunk.delta.text, end = "")
            
            
            
# ------------------------            
# anthropic result of streaming messages.
# RawMessageStartEvent(message=Message(id='msg_011Cd4Vdqvn3GRaZZ8TEyR8S', container=None, content=[], model='claude-sonnet-4-6', role='assistant', stop_details=None, stop_reason=None, stop_sequence=None, type='message', usage=Usage(cache_creation=CacheCreation(ephemeral_1h_input_tokens=0, ephemeral_5m_input_tokens=0), cache_creation_input_tokens=0, cache_read_input_tokens=0, inference_geo='global', input_tokens=11, output_tokens=1, output_tokens_details=None, server_tool_use=None, service_tier='standard')), type='message_start')
# RawContentBlockStartEvent(content_block=TextBlock(citations=None, text='', type='text'), index=0, type='content_block_start')
# RawContentBlockDeltaEvent(delta=TextDelta(text='Hello', type='text_delta'), index=0, type='content_block_delta')
# TextEvent(type='text', text='Hello', snapshot='Hello')
# RawContentBlockDeltaEvent(delta=TextDelta(text=', World! 👋\n\nIs there something I can help you with today?', type='text_delta'), index=0, type='content_block_delta')
# TextEvent(type='text', text=', World! 👋\n\nIs there something I can help you with today?', snapshot='Hello, World! 👋\n\nIs there something I can help you with today?')
# ParsedContentBlockStopEvent(index=0, type='content_block_stop', content_block=ParsedTextBlock(citations=None, text='Hello, World! 👋\n\nIs there something I can help you with today?', type='text', parsed_output=None))
# RawMessageDeltaEvent(delta=Delta(container=None, stop_details=None, stop_reason='end_turn', stop_sequence=None), type='message_delta', usage=MessageDeltaUsage(cache_creation_input_tokens=0, cache_read_input_tokens=0, input_tokens=11, output_tokens=21, output_tokens_details=None, server_tool_use=None))
# ParsedMessageStopEvent(type='message_stop', message=ParsedMessage(id='msg_011Cd4Vdqvn3GRaZZ8TEyR8S', container=None, content=[ParsedTextBlock(citations=None, text='Hello, World! 👋\n\nIs there something I can help you with today?', type='text', parsed_output=None)], model='claude-sonnet-4-6', role='assistant', stop_details=None, stop_reason='end_turn', stop_sequence=None, type='message', usage=Usage(cache_creation=CacheCreation(ephemeral_1h_input_tokens=0, ephemeral_5m_input_tokens=0), cache_creation_input_tokens=0, cache_read_input_tokens=0, inference_geo='global', input_tokens=11, output_tokens=21, output_tokens_details=None, server_tool_use=None, service_tier='standard')))
# ------------------------