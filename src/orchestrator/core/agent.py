from orchestrator.providers.base import Provider
from orchestrator.core.tool_registry import ToolRegistry
from orchestrator.core.chat_request import ChatRequest
from orchestrator.core.chat_message import Message

class Agent:
    
    def __init__(self, provider: Provider, model: str, tool_registry: ToolRegistry, max_iterations: int = 10):
        self.max_iterations = max_iterations
        self.provider = provider
        self.tool_registry = tool_registry
        self.model = model
        
    def run(self, prompt : str) -> str :
        state = [
            Message(role="system", content="You are a helpful assistant."),
            Message(role="user", content=prompt),
        ]
        tools = [
            {"name": t.name, "description": t.description, "parameters": t.parameters}
            for t in self.tool_registry.all()
        ] or None

        iteration = 0
        while True:
            if(iteration == self.max_iterations):
                raise RuntimeError("Max retry reached. Quitting loop.")
            iteration+=1
            request = ChatRequest(
                model= self.model,
                messages= state,
                temperature= 0.3,
                tools= tools,
            )
            response = self.provider.complete(request)
            if response.stop_reason == "final": 
                return response.content
            
            state.append(Message( 
                role = "assistant",
                content= response.content,
                tool_calls= response.tool_calls
            ))
            
            for t in response.tool_calls:
                func_name = t["name"]
                tool = self.tool_registry.get(func_name)
                try:
                    result = tool.func(**t["arguments"])
                except Exception as e:
                    result = f"Error executing tool {func_name}: {str(e)}"
                state.append(Message(
                    role= "tool",
                    tool_call_id= t["id"],
                    content= str(result)
                    )
                )

            
            
        
        
    