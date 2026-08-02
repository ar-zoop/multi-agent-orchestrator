from dataclasses import dataclass


@dataclass
class UsageStats:
    cost: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    calls: int = 0
