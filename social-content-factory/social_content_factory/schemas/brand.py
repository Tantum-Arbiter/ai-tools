from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

AspectRatio = Literal["1x1", "4x5", "9x16", "1.91x1"]
LLMProvider = Literal["phi4", "openai"]


class BrandIngest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    github_repos: list[str] = Field(default_factory=list)
    min_score: float = Field(default=0.5, ge=0.0, le=1.0)


class Brand(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    key: str = Field(min_length=1)
    name: str = Field(min_length=1)
    voice: str = Field(min_length=1)
    audience: str = Field(min_length=1)
    visual_style: str = Field(min_length=1)
    negative_prompts: list[str] = Field(min_length=1)
    default_formats: list[AspectRatio] = Field(min_length=1)
    allow_auto_publish: bool = False
    llm_provider: LLMProvider = "phi4"
    draft: bool = False
    ingest: BrandIngest | None = None

    @field_validator("key")
    @classmethod
    def key_is_slug(cls, value: str) -> str:
        normalised = value.lower()
        if not normalised.replace("-", "").replace("_", "").isalnum():
            raise ValueError("brand key must be a slug (alphanumeric, '-' or '_' only)")
        return normalised
