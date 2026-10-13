# -*- coding: utf-8 -*-
"""接口出入参模型。统一响应格式 {code, status, data}。"""

import datetime as dt
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


def _this_year() -> int:
    """流年默认值取服务端当前年，避免把年份写死在代码里。"""
    return dt.date.today().year


class DiagnoseRequest(BaseModel):
    degree: float = Field(..., ge=0, lt=360, description="手机读取的磁方位角")
    declination: float = Field(0.0, ge=-30, le=30, description="当地磁偏角")
    year: int = Field(
        default_factory=_this_year, ge=1900, le=2100, description="流年（默认当前年）"
    )
    house_name: str = Field("我的房屋", description="房屋名称")
    layout: str = Field("", max_length=20, description="户型，如「3室2厅」（用于生成布局建议表）")
    area: float = Field(0.0, ge=0, description="建筑面积，0 表示未填")
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
    tips: list = Field(default_factory=list, description="家具摆放建议（按当日吉凶生成）")
    layout_guide: list = Field(
        default_factory=list, description="按户型生成的功能区布局建议表"
    )
    rules_version: str = Field("", description="本次计算所采用的规则集版本")


# ---------------------------------------------------------------- 房屋档案
class RoomIn(BaseModel):
    """房间档案：房间名 + 所在宫位（0..8，与客户端 RoomProfile 一致）。"""

    id: str = Field("", max_length=64, description="房间 id，为空则由服务端生成")
    name: str = Field("", max_length=20, description="房间名，如 主卧")
    cell: int = Field(4, ge=0, le=8, description="宫位索引 0..8")


class HouseIn(BaseModel):
    """新建 / 保存房屋。id 为空表示新建，由服务端生成。"""

    id: str = Field("", max_length=64, description="房屋 id，为空则由服务端生成")
    name: str = Field(..., min_length=1, max_length=60, description="房屋名称")
    layout: str = Field("", max_length=20, description="户型，如 3室2厅")
    area: float = Field(0.0, ge=0, description="建筑面积")
    # None 表示尚未测量；入库前统一归一化到 [0, 360)
    degree: Optional[float] = Field(None, description="磁北读数，None = 未测量")
    declination: float = Field(0.0, ge=-30, le=30, description="当地磁偏角")
    year: Optional[int] = Field(None, ge=1900, le=2100, description="流年，默认当前年")
    rooms: list[RoomIn] = Field(default_factory=list, description="房间布局")


class HousePatch(BaseModel):
    """局部更新，用于罗盘测量后回写坐向等单字段改动。"""

    degree: Optional[float] = Field(None, description="磁北读数")
    declination: Optional[float] = Field(None, ge=-30, le=30, description="当地磁偏角")
    name: Optional[str] = Field(None, min_length=1, max_length=60)
    layout: Optional[str] = Field(None, max_length=20)
    area: Optional[float] = Field(None, ge=0)
    rooms: Optional[list[RoomIn]] = Field(None)


class HouseOut(BaseModel):
    """房屋出参；degree 为 null 表示尚未测量。"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    layout: str = ""
    area: float = 0.0
    degree: Optional[float] = None
    declination: float = 0.0
    year: int = 0
    rooms: list[RoomIn] = Field(default_factory=list)


# ---------------------------------------------------------------- 八字排盘
class BaziRequest(BaseModel):
    """排盘入参：公历出生时刻 + 出生地经度（用于真太阳时校正）。"""

    year: int = Field(..., ge=1900, le=2100, description="出生年（公历）")
    month: int = Field(..., ge=1, le=12, description="出生月（公历 1-12）")
    day: int = Field(..., ge=1, le=31, description="出生日（公历 1-31）")
    hour: int = Field(..., ge=0, le=23, description="出生小时（北京时间 0-23）")
    minute: int = Field(0, ge=0, le=59, description="出生分钟（0-59）")
    # 性别与经度直接决定排盘结果，必须显式传入，不能用默认值冒充用户资料
    gender: str = Field(..., pattern=r"^(男|女)$", description="性别：男 / 女（必传）")
    longitude: float = Field(
        ..., ge=73.0, le=135.0,
        description="出生地东经度数，用于真太阳时校正（每度 4 分钟）（必传）",
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


# ---------------------------------------------------------------- 用户 / 认证
PHONE_PATTERN = r"^1[3-9]\d{9}$"


class SendCodeRequest(BaseModel):
    """请求发送短信验证码。"""

    phone: str = Field(..., pattern=PHONE_PATTERN, description="中国大陆手机号")
    scene: str = Field("login", max_length=20, description="业务场景，默认登录")


class LoginRequest(BaseModel):
    """手机号 + 验证码登录；用户不存在时自动注册。"""

    phone: str = Field(..., pattern=PHONE_PATTERN)
    code: str = Field(..., min_length=4, max_length=8, description="短信验证码")


class UserOut(BaseModel):
    """App 用户出参（App 端与后台共用）。"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    phone: str
    nickname: str = ""
    avatar: str = ""
    status: str = "active"
    ban_reason: str = ""
    remark: str = ""
    login_count: int = 0
    last_login_at: Optional[dt.datetime] = None
    created_at: Optional[dt.datetime] = None


class UserProfileUpdate(BaseModel):
    """用户自助修改资料。"""

    nickname: Optional[str] = Field(None, max_length=40)
    avatar: Optional[str] = Field(None, max_length=255)


class LoginOut(BaseModel):
    """登录成功返回：token + 用户资料，客户端一次拿全。"""

    token: str
    token_type: str = "Bearer"
    expires_in: int = Field(0, description="token 有效期（秒）")
    user: UserOut


# ---------------------------------------------------------------- 管理后台
class AdminLoginRequest(BaseModel):
    """管理员账号密码登录。"""

    username: str = Field(..., min_length=1, max_length=40)
    password: str = Field(..., min_length=6, max_length=64)


class AdminOut(BaseModel):
    """管理员信息，绝不包含密码哈希。"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    username: str
    display_name: str = ""
    status: str = "active"
    last_login_at: Optional[dt.datetime] = None


class AdminLoginOut(BaseModel):
    token: str
    token_type: str = "Bearer"
    expires_in: int = 0
    admin: AdminOut


class PageMeta(BaseModel):
    """统一分页信封。"""

    total: int = 0
    page: int = 1
    size: int = 20
    pages: int = 0


class AdminUserItem(UserOut):
    """后台列表项：用户资料 + 名下房屋数。"""

    house_count: int = 0


class AdminUserPage(BaseModel):
    page_meta: PageMeta
    items: list[AdminUserItem]


class UserStatusUpdate(BaseModel):
    """封禁 / 解封。value 只允许 active 或 banned。"""

    status: str = Field(..., pattern=r"^(active|banned)$")
    reason: str = Field("", max_length=200, description="封禁原因，解封时可留空")


class UserRemarkUpdate(BaseModel):
    """运营备注。"""

    remark: str = Field("", max_length=200)


class AdminHouseItem(BaseModel):
    """后台房屋视图：多了归属用户信息。"""

    id: str
    owner_id: Optional[str] = None
    owner_phone: str = ""
    owner_nickname: str = ""
    name: str = ""
    layout: str = ""
    area: float = 0.0
    degree: Optional[float] = None
    year: int = 0
    room_count: int = 0
    created_at: Optional[dt.datetime] = None
    updated_at: Optional[dt.datetime] = None


class AdminHousePage(BaseModel):
    page_meta: PageMeta
    items: list[AdminHouseItem]


class TrendPoint(BaseModel):
    """趋势图的一个数据点。"""

    date: str = Field("", description="YYYY-MM-DD")
    new_users: int = 0


class StatsOut(BaseModel):
    """后台看板统计。"""

    total_users: int = 0
    new_today: int = 0
    new_7d: int = 0
    active_7d: int = 0
    banned_users: int = 0
    total_houses: int = 0
    measured_houses: int = Field(0, description="已完成罗盘测量的房屋数")
    trend: list[TrendPoint] = Field(default_factory=list, description="近 14 天新增")


# ---------------------------------------------------------------- 命理档案
class BaziProfileIn(BaseModel):
    """保存命理档案的入参：出生时刻 + 出生地。

    与 BaziRequest 保持同名字段，便于 App 端一次录入同时排盘与存档；
    province / city 只用于回显与后台展示，不参与计算。
    """

    year: int = Field(..., ge=1900, le=2100, description="出生年（公历）")
    month: int = Field(..., ge=1, le=12, description="出生月（公历 1-12）")
    day: int = Field(..., ge=1, le=31, description="出生日（公历 1-31）")
    hour: int = Field(..., ge=0, le=23, description="出生小时（北京时间 0-23）")
    minute: int = Field(0, ge=0, le=59, description="出生分钟（0-59）")
    gender: str = Field(..., pattern=r"^(男|女)$", description="性别：男 / 女")
    longitude: float = Field(
        ..., ge=73.0, le=135.0,
        description="出生地东经度数，用于真太阳时校正（必传，不兜底）",
    )
    name: str = Field("", max_length=20, description="姓名（可选）")
    province: str = Field("", max_length=20, description="出生地省份，如 广东")
    city: str = Field("", max_length=30, description="出生地城市，如 广州")


class BaziProfileOut(BaziProfileIn):
    """命理档案出参：多了记录 id、四柱摘要与时间戳。"""

    model_config = ConfigDict(from_attributes=True)

    id: str = ""
    pillars: str = Field("", description="四柱摘要，如「辛未 丁酉 癸未 丙辰」")
    created_at: Optional[dt.datetime] = None
    updated_at: Optional[dt.datetime] = None


class AdminBaziProfileItem(BaziProfileOut):
    """后台命理档案列表项：多了归属用户信息。"""

    owner_id: Optional[str] = None
    owner_phone: str = ""
    owner_nickname: str = ""


class AdminBaziProfilePage(BaseModel):
    page_meta: PageMeta
    items: list[AdminBaziProfileItem]


# ---------------------------------------------------------------- 紫微斗数
class ZiweiRequest(BaziRequest):
    """紫微排盘入参：与八字排盘完全一致（同一份出生信息，两种算法）。

    紫微同样以真太阳时定时辰，因此经度必传、不做默认值兜底。
    """


class ZiweiPalace(BaseModel):
    """紫微十二宫之一：宫名、宫位干支与星曜。"""

    name: str = ""
    zhi: str = ""
    gan: str = ""
    pillar: str = ""
    main: list[str] = Field(default_factory=list, description="主星（可能两颗同宫）")
    aux: list[str] = Field(default_factory=list, description="辅星")
    si_hua: list[dict] = Field(default_factory=list, description="四化：[{star, hua}]")
    is_ming: bool = False
    is_shen: bool = False
    is_empty: bool = Field(False, description="空宫（无主星，需借对宫参看）")
    da_xian: dict = Field(default_factory=dict, description="该宫对应的大限年龄段")


class ZiweiResponse(BaseModel):
    """紫微命盘 + 感情 / 职业 / 运势解读。"""

    birth: dict = Field(default_factory=dict, description="出生信息（含真太阳时）")
    basic: dict = Field(
        default_factory=dict,
        description="命宫 / 身宫 / 五行局 / 紫微落宫等基本信息",
    )
    palaces: list[ZiweiPalace] = Field(default_factory=list)
    da_xian: dict = Field(default_factory=dict, description="当前十年大限")
    san_fang: dict = Field(default_factory=dict, description="三方四正")
    reading: dict = Field(
        default_factory=dict,
        description="感情 / 职业 / 运势三段解读",
    )
    years: list[dict] = Field(
        default_factory=list,
        description="逐年流年运势（默认自今年起 10 年）",
    )
