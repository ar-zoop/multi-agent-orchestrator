from abc import ABC, abstractmethod

class Provider(ABC):         

    @abstractmethod
    def complete(self, request):
        pass