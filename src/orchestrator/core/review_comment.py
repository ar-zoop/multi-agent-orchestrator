from pydantic import BaseModel

class ReviewComment(BaseModel):
    file : str
    line : int
    severity : str
    comment : str