from typing import Literal

Period = Literal["today", "24h", "7d"]
PresetPeriod = Period | Literal["30d", "90d"]
