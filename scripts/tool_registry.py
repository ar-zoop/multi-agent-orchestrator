class ToolRegistry:
    _tools : dict
    def __init__(self): 
        self._tools ={}

    def register(self, tool):
        self._tools[tool.name] = tool
        
    def get(self, name):
        return self._tools[name]