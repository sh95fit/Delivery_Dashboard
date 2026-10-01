from typing import Literal

from pydantic import BaseModel, Field


class AddInternalTargetRequest(BaseModel):
    kind: Literal["address", "account"]
    target_id: int = Field(gt=0)
    memo: str | None = Field(default=None, max_length=200)
