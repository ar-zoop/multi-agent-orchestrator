from abc import ABC, abstractmethod

class Provider(ABC):         

    @abstractmethod
    def complete(self, request):
        pass
    
    @abstractmethod
    def stream(self, request):
        pass