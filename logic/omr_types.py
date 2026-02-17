from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class Marker:
    cx: int
    cy: int
    x: int = 0
    y: int = 0
    w: int = 0
    h: int = 0
    solidity: float = 0.0
    fill_ratio: float = 0.0
    ring_ratio: float = 1.0
    interpolated: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return {
            "cx": int(self.cx),
            "cy": int(self.cy),
            "x": int(self.x),
            "y": int(self.y),
            "w": int(self.w),
            "h": int(self.h),
            "solidity": float(self.solidity),
            "fill_ratio": float(self.fill_ratio),
            "ring_ratio": float(self.ring_ratio),
            "interpolated": bool(self.interpolated),
        }

    @staticmethod
    def from_obj(obj: Any) -> "Marker":
        if isinstance(obj, Marker):
            return obj
        if isinstance(obj, dict):
            return Marker(
                cx=int(obj.get("cx", 0)),
                cy=int(obj.get("cy", 0)),
                x=int(obj.get("x", 0)),
                y=int(obj.get("y", 0)),
                w=int(obj.get("w", 0)),
                h=int(obj.get("h", 0)),
                solidity=float(obj.get("solidity", 0.0)),
                fill_ratio=float(obj.get("fill_ratio", 0.0)),
                ring_ratio=float(obj.get("ring_ratio", 1.0)),
                interpolated=bool(obj.get("interpolated", False)),
            )
        return Marker(cx=0, cy=0)


@dataclass
class QuestionResult:
    q_num: int
    marked: List[int] = field(default_factory=list)
    status: str = "공란"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "q_num": int(self.q_num),
            "marked": list(self.marked),
            "status": str(self.status),
        }
