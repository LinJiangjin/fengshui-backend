# -*- coding: utf-8 -*-
"""确定性规则引擎（L1）。

不依赖任何大模型，输出可复现、可单元测试。
"""

from .compass import orient, degree_to_mountain, normalize_degree  # noqa: F401
from .bazhai import (  # noqa: F401
    build_bazhai,
    lichun_year,
    ming_gua_number,
    ming_gua_of,
    you_nian_of,
    zhai_gua_of,
)
from .flying_star import (  # noqa: F401
    build_palaces,
    center_star_of_year,
    pick_extremes,
    score_of,
)
from .daily_star import (  # noqa: F401
    build_daily_palaces,
    center_star_of_date,
    daily_chart,
    dongzhi_of,
    escape_of,
    jiazi_offset,
    resolve_date,
    solar_term_range_of,
    xiazhi_of,
    yuan_of,
)
from .advice import (  # noqa: F401
    build_advice,
    build_daily_advice,
    build_furniture_tips,
    build_layout_guide,
    build_metrics,
    enhance,
)
from .almanac import (  # noqa: F401
    activity_of,
    day_almanac,
    day_score,
    list_activities,
    month_overview,
    parse_date,
    resolve_day,
    select_dates,
)
from .ziwei import (  # noqa: F401
    build_ziwei,
    palace_gan,
    wu_xing_ju,
    ziwei_palace,
)
from .ziwei_reading import build_ziwei_reading  # noqa: F401
from .ziwei_year import build_ziwei_years, gan_zhi_of_year  # noqa: F401
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
