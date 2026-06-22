from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from social_content_factory.schemas.brand import AspectRatio


class Theme(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    slug: str = Field(min_length=1)
    title: str = Field(min_length=1)
    subject: str = Field(min_length=1)
    narrative: str | None = None
    tags: list[str] = Field(default_factory=list)
    cta: str | None = None
    format_overrides: list[AspectRatio] | None = None

    @field_validator("slug")
    @classmethod
    def slug_is_slug(cls, value: str) -> str:
        normalised = value.lower()
        if not normalised.replace("-", "").replace("_", "").isalnum():
            raise ValueError("theme slug must be a slug (alphanumeric, '-' or '_' only)")
        return normalised
