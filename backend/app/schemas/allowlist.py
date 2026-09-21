from pydantic import BaseModel, Field


class AddAllowlistRequest(BaseModel):
    kind: str = Field(pattern="^(email|domain)$")
    value: str = Field(min_length=1, max_length=255)
