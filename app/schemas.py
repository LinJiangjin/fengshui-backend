# -*- coding: utf-8 -*-
"""接口出入参模型。统一响应格式 {code, status, data}。"""

from pydantic import BaseModel, Field


class DiagnoseRequest(BaseModel):
    degree: float = Field(..., ge=0, lt=360, description="手机读取的磁方位角")
    declination: float = Field(0.0, ge=-30, le=30, description="当地磁偏角")
    year: int = Field(2026, ge=1900, le=2100, description="流年")
    house_name: str = Field("我的房屋", description="房屋名称")
    area: float = Field(96.0, gt=0, description="建筑面积")
    month: int = Field(0, ge=0, le=12, description="测算月份，0 表示今天（用于日家紫白）")
    day: int = Field(0, ge=0, le=31, description="测算日期，0 表示今天（用于日家紫白）")


class DiagnoseResponse(BaseModel):
    score: int
    orientation: dict
    palaces: list
    extremes: dict
    metrics: list
    advice: list
    year: int
    house_name: str
    area: float
    daily: dict = Field(default_factory=dict, description="当日紫白盘：今日吉位 / 今日忌方")


# ---------------------------------------------------------------- 八字排盘
class BaziRequest(BaseModel):
    """排盘入参：公历出生时刻 + 出生地经度（用于真太阳时校正）。"""

    year: int = Field(..., ge=1900, le=2100, description="出生年（公历）")
    month: int = Field(..., ge=1, le=12, description="出生月（公历 1-12）")
    day: int = Field(..., ge=1, le=31, description="出生日（公历 1-31）")
    hour: int = Field(..., ge=0, le=23, description="出生小时（北京时间 0-23）")
    minute: int = Field(0, ge=0, le=59, description="出生分钟（0-59）")
    gender: str = Field("男", pattern=r"^(男|女)$", description="性别：男 / 女")
    longitude: float = Field(
        120.0, ge=73.0, le=135.0,
        description="出生地东经度数，用于真太阳时校正（每度 4 分钟）",
    )
    name: str = Field("", max_length=20, description="姓名（可选，仅作档案回显）")


class BaziHiddenGan(BaseModel):
    """地支藏干条目。"""

    gan: str = Field("", description="藏干天干")
    element: str = Field("", description="藏干五行")
    role: str = Field("", description="本气 / 中气 / 余气")
    weight: float = Field(0.0, description="计分权重：本气 1.0、中气 0.6、余气 0.3")


class BaziPillar(BaseModel):
    """一柱：天干 + 地支 + 藏干 + 纳音 + 十神。"""

    key: str = Field("", description="year / month / day / time")
    name: str = Field("", description="年柱 / 月柱 / 日柱 / 时柱")
    gan: str = Field("", description="天干")
    zhi: str = Field("", description="地支")
    pillar: str = Field("", description="干支合写，如 戊辰")
    gan_element: str = Field("", description="天干五行")
    zhi_element: str = Field("", description="地支五行")
    hidden: list[BaziHiddenGan] = Field(default_factory=list, description="地支藏干明细")
    hidden_text: str = Field("", description="藏干合写，如 戊乙癸")
    na_yin: str = Field("", description="纳音五行")
    gan_shi_shen: str = Field("", description="天干十神")


class BaziElement(BaseModel):
    """五行占比条目。"""

    element: str = Field("", description="木 / 火 / 土 / 金 / 水")
    percent: int = Field(0, ge=0, le=100, description="占比百分比，五项合计 100")
    score: float = Field(0.0, description="加权原始分")
    color_key: str = Field("", description="前端配色 key：wood/fire/earth/metal/water")


class BaziGod(BaseModel):
    """喜用神 / 忌神条目。"""

    element: str = Field("", description="五行")
    label: str = Field("", description="展示文案，如「金 · 收敛」")
    reason: str = Field("", description="取用理由，如「财星耗身」")
    percent: int = Field(0, ge=0, le=100, description="该五行在命局中的占比")
    color_key: str = Field("", description="前端配色 key")


class BaziBirth(BaseModel):
    """出生信息摘要（含真太阳时校正结果）。"""

    name: str = Field("", description="姓名")
    gender: str = Field("男", description="男 / 女")
    longitude: float = Field(120.0, description="出生地东经度数")
    solar: str = Field("", description="钟表时间（北京时间）")
    true_solar: str = Field("", description="真太阳时（校正后）")
    offset_minutes: float = Field(0.0, description="校正偏移分钟数")
    hour_zhi: str = Field("", description="时辰地支，如 辰")
    is_night_zi: bool = Field(False, description="是否为夜子时（23:00-01:00）")
    solar_term_range: str = Field("", description="所处节气区间，如「惊蛰后 · 春分前」")
    summary: str = Field("", description="卡片副标题，如「1988.03.12 辰时 · 男」")


class BaziDayMaster(BaseModel):
    """日主信息。"""

    gan: str = Field("", description="日干")
    zhi: str = Field("", description="日支")
    element: str = Field("", description="日主五行")
    pillar: str = Field("", description="日柱干支")


class BaziStrength(BaseModel):
    """日主强弱判定结果。"""

    level: str = Field("", description="偏强 / 中和 / 偏弱")
    score: float = Field(0.0, description="加权总分")
    detail: dict = Field(default_factory=dict, description="得令/得地/得势明细")


class BaziResponse(BaseModel):
    """排盘结果。所有数值由 bazi 引擎确定性算出，不经过大模型。"""

    birth: BaziBirth
    day_master: BaziDayMaster
    pillars: list[BaziPillar]
    elements: list[BaziElement]
    element_summary: str = Field("", description="五行卡副标题，如「日主丙火 · 木旺缺金」")
    strength: BaziStrength
    favorable: list[BaziGod] = Field(default_factory=list, description="喜用神")
    unfavorable: list[BaziGod] = Field(default_factory=list, description="忌神")
