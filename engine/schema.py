"""
Lightweight Schema for Aesthetic Compiler Design Packs.
Uses built-in dataclasses for zero-dependency portability.
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

@dataclass
class Dimensions:
    format: str = "A4"
    width_mm: float = 210.0
    height_mm: float = 297.0
    orientation: str = "portrait"

@dataclass
class Margins:
    top: float = 20.0
    right: float = 20.0
    bottom: float = 20.0
    left: float = 20.0

@dataclass
class TargetSpec:
    dimensions: Dimensions = field(default_factory=Dimensions)
    margins_mm: Margins = field(default_factory=Margins)

@dataclass
class TypographySpec:
    primaryFont: str = "Inter"
    displayFont: Optional[str] = "Inter Tight"
    monospaceFont: Optional[str] = "Space Mono"
    modularScale: float = 1.25
    lineHeightBase: float = 1.45

@dataclass
class SpatialBudget:
    maxLineItems: Optional[int] = None
    maxNotesChars: Optional[int] = None
    maxHeadlineLines: Optional[int] = None
    strictSinglePage: bool = True
    extra: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SpatialBudget":
        known = {
            "maxLineItems": d.get("maxLineItems"),
            "maxNotesChars": d.get("maxNotesChars"),
            "maxHeadlineLines": d.get("maxHeadlineLines"),
            "strictSinglePage": d.get("strictSinglePage", True)
        }
        extra = {k: v for k, v in d.items() if k not in known}
        return cls(**known, extra=extra)

@dataclass
class DesignPackSpec:
    id: str
    name: str
    version: str = "1.0.0"
    category: str = "Editorial"
    description: str = ""
    target: TargetSpec = field(default_factory=TargetSpec)
    typography: TypographySpec = field(default_factory=TypographySpec)
    colorTokens: Dict[str, str] = field(default_factory=dict)
    spatialBudget: SpatialBudget = field(default_factory=SpatialBudget)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "DesignPackSpec":
        target_raw = d.get("target", {})
        dims_raw = target_raw.get("dimensions", {})
        margins_raw = target_raw.get("margins_mm", {})
        
        target = TargetSpec(
            dimensions=Dimensions(**dims_raw) if dims_raw else Dimensions(),
            margins_mm=Margins(**margins_raw) if margins_raw else Margins()
        )
        
        typo_raw = d.get("typography", {})
        typography = TypographySpec(**typo_raw) if typo_raw else TypographySpec()
        
        budget_raw = d.get("spatialBudget", {})
        budget = SpatialBudget.from_dict(budget_raw) if budget_raw else SpatialBudget()
        
        return cls(
            id=d["id"],
            name=d["name"],
            version=d.get("version", "1.0.0"),
            category=d.get("category", "Editorial"),
            description=d.get("description", ""),
            target=target,
            typography=typography,
            colorTokens=d.get("colorTokens", {}),
            spatialBudget=budget
        )
