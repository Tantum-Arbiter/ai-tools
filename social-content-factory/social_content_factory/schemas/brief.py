from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from social_content_factory.schemas.brand import AspectRatio


class Brief(BaseModel):
    model_config = ConfigDict(extra="forbid")

    brand_key: str = Field(min_length=1)
    theme_slug: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    negative_prompt: str = Field(min_length=1)
    formats: list[AspectRatio] = Field(min_length=1)
    seed: int = Field(ge=0, lt=2**32)
    prompt_hash: str = Field(min_length=16, max_length=16)
