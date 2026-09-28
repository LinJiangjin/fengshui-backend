# -*- coding: utf-8 -*-
"""确定性规则引擎（L1）。

不依赖任何大模型，输出可复现、可单元测试。
"""

from .compass import orient, degree_to_mountain, normalize_degree  # noqa: F401
from .flying_star import (  # noqa: F401
    build_palaces,
    center_star_of_year,
    pick_extremes,
    score_of,
)
from .advice import build_advice, build_metrics, enhance  # noqa: F401
from .bazi import (  # noqa: F401
    apply_night_zi_fix,
    build_bazi,
    day_pillar_from_anchor,
    element_summary_of,
    enhance as enhance_bazi,
    hour_branch_of,
    hour_pillar_gan,
    jiazi_index,
    judge_strength,
    na_yin_of,
    pick_gods,
    relation_of,
    score_elements,
    shi_shen_of,
    to_percent,
    true_solar_time,
)
