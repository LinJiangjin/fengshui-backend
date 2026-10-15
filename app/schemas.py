# -*- coding: utf-8 -*-
"""接口出入参模型。统一响应格式 {code, status, data}。"""

import datetime as dt
from typing import Annotated, Optional

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


class DeleteAccountRequest(BaseModel):
    """注销账号入参。

    confirm 必须是显式的 True——注销不可恢复，不允许「空 body 直接打过来」
    这种误触路径。
    """

    confirm: bool = Field(False, description="必须显式传 true 才会执行注销")


class DeleteAccountOut(BaseModel):
    """注销结果：回报各类数据的清理数量，便于客服核对与客户端提示。"""

    deleted: bool = True
    user_id: str = ""
    removed_bazi_profiles: int = 0
    removed_houses: int = 0
    removed_sms_codes: int = 0


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


# ---------------------------------------------------------------- 方案库（运营内容）
# 色值统一 #RRGGBB；五行限定 木火土金水——这两条卡在入参上，
# 免得后台填进来的脏数据把 App 端渲染搞坏（客户端按定长解析 hex）。
HEX_PATTERN = r"^#[0-9A-Fa-f]{6}$"
ELEMENT_PATTERN = r"^(木|火|土|金|水)$"

# 单条亮点文案，避免运营把一整篇文章塞进一个条目
HighlightText = Annotated[str, Field(min_length=1, max_length=140)]


class SchemeColorIn(BaseModel):
    """方案主色板里的一块色。"""

    name: str = Field(..., min_length=1, max_length=20)
    hex: str = Field(..., pattern=HEX_PATTERN)


class SchemeRoomIn(BaseModel):
    """分区配色建议：某个房间用什么色、怎么用。"""

    name: str = Field(..., min_length=1, max_length=20)
    hex: str = Field(..., pattern=HEX_PATTERN)
    note: str = Field("", max_length=120)


class SchemeIn(BaseModel):
    """方案的创建 / 全量更新入参。

    色值字段命名为 from_color / to_color——`from` 是 Python 关键字，不能作列名；
    下发到 App 时由 routers/library.py 映射回 from / to。
    """

    title: str = Field(..., min_length=1, max_length=60)
    subtitle: str = Field("", max_length=80, description="如「五行属木 · 96㎡」")
    tag: str = Field(..., min_length=1, max_length=20, description="风格标签，如「新中式」")
    element: str = Field(..., pattern=ELEMENT_PATTERN, description="五行：木 火 土 金 水")
    area: int = Field(0, ge=0, le=1000, description="建筑面积（㎡）")
    from_color: str = Field(..., pattern=HEX_PATTERN, description="卡片渐变起始色")
    to_color: str = Field(..., pattern=HEX_PATTERN, description="卡片渐变结束色")
    summary: str = Field("", max_length=300)
    highlights: list[HighlightText] = Field(default_factory=list, max_length=12)
    colors: list[SchemeColorIn] = Field(default_factory=list, max_length=12)
    rooms: list[SchemeRoomIn] = Field(default_factory=list, max_length=16)
    published: bool = Field(True, description="是否上架；下架后 App 端不可见")
    sort_order: int = Field(0, ge=0, le=9999, description="展示顺序，越小越靠前")


class AdminSchemeItem(SchemeIn):
    """后台方案出参：多了 id 与时间戳。"""

    model_config = ConfigDict(from_attributes=True)

    id: str = ""
    created_at: Optional[dt.datetime] = None
    updated_at: Optional[dt.datetime] = None


class AdminSchemePage(BaseModel):
    page_meta: PageMeta
    items: list[AdminSchemeItem]


class SchemeStatusUpdate(BaseModel):
    """上架 / 下架。"""

    published: bool


class ElementNoteItem(BaseModel):
    """五行宜忌解读。"""

    model_config = ConfigDict(from_attributes=True)

    element: str = ""
    fit: str = ""
    avoid: str = ""
    sort_order: int = 0


class ElementNoteUpdate(BaseModel):
    """更新某一行五行的解读文案。"""

    fit: str = Field("", max_length=200)
    avoid: str = Field("", max_length=200)


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


# ---------------------------------------------------------------- 八宅游年
class BazhaiRequest(BaseModel):
    """八宅排盘入参：出生年 + 性别定命卦，坐向（或宅卦）定宅卦。

    宅卦二者取一：给了 ``degree`` 就用罗盘度数推算（顺带返回坐向明细），
    否则用 ``trigram`` 直接指定。两者都缺时接口返回 400。

    命卦以立春为界，因此 `month`/`day` 传了就会用于分界；
    只传年份（month=day=0）则按整年计，不做分界。
    """

    year: int = Field(..., ge=1900, le=2100, description="出生年（公历）")
    gender: str = Field(..., pattern=r"^(男|女)$", description="性别：男 / 女（必传）")
    month: int = Field(0, ge=0, le=12, description="出生月（用于立春分界），0 表示不分界")
    day: int = Field(0, ge=0, le=31, description="出生日（用于立春分界），0 表示不分界")
    hour: int = Field(0, ge=0, le=23, description="出生小时（用于立春分界）")
    minute: int = Field(0, ge=0, le=59, description="出生分钟（用于立春分界）")
    degree: Optional[float] = Field(
        None, ge=0, lt=360, description="手机读取的磁方位角；为空则用 trigram"
    )
    declination: float = Field(0.0, ge=-30, le=30, description="当地磁偏角")
    trigram: str = Field(
        "", max_length=4, description="直接指定宅卦（坐山卦），如「坎」；degree 为空时使用"
    )
    name: str = Field("", max_length=20, description="姓名（可选，仅作档案回显）")


class BazhaiBirth(BaseModel):
    """八宅所用的出生信息（含立春分界结果）。"""

    year: int = Field(0, description="出生年（公历）")
    month: int = 0
    day: int = 0
    gender: str = Field("男", description="男 / 女")
    name: str = ""
    solar_year: int = Field(
        0, description="命卦归属年份：立春前出生为上一年"
    )
    lichun_adjusted: bool = Field(False, description="是否因立春而回退到上一年")
    summary: str = Field("", description="卡片副标题，如「1990 年生 · 男 · 东四命」")


class BazhaiGua(BaseModel):
    """命卦 / 宅卦的公共字段。"""

    trigram: str = Field("", description="八卦名：乾坎艮震巽离坤兑")
    name: str = Field("", description="如「坎命」「坎宅」")
    luoshu: int = Field(0, ge=0, le=9, description="洛书数 1-9")
    direction: str = Field("", description="卦位方位，如「正北」")
    group: str = Field("", description="东四命 / 西四命 / 东四宅 / 西四宅")
    label: str = Field("", description="展示用组合文案，如「坎命 · 东四命」")


class MingGuaOut(BazhaiGua):
    """本命卦：命卦只由出生年与性别决定，含东西四分组与调整说明。"""

    number: int = Field(0, ge=0, le=9, description="命卦洛书数（余 5 男寄坤 2、女寄艮 8）")
    group_key: str = Field("", description="东四 / 西四")
    solar_year: int = 0
    lichun_adjusted: bool = False
    name_input: str = ""
    summary: str = ""
    note: str = ""


class ZhaiGuaOut(BazhaiGua):
    """宅卦：以坐山卦定；未提供度数时坐向明细为空。"""

    group_key: str = ""
    description: str = Field("", description="坐向吉凶评语")
    mountain: str = Field("", description="坐山，如「子」")
    facing: str = Field("", description="向山，如「午」")
    title: str = Field("", description="坐向合写，如「子山午向」")
    readable: str = Field("", description="如「坐北朝南」")
    facing_trigram: str = ""
    facing_direction: str = ""
    degree: Optional[float] = None


class BazhaiStar(BaseModel):
    """游年八星之一。level 复用九星四档，前端配色可直接沿用。"""

    code: str = Field("", description="生 / 天 / 延 / 伏 / 祸 / 六 / 五 / 绝")
    star: str = Field("", description="生气 / 天医 / 延年 / 伏位 / 祸害 / 六煞 / 五鬼 / 绝命")
    alias: str = Field("", description="星曜别名，如「贪狼」")
    element: str = Field("", description="五行")
    level: str = Field("", description="旺 / 平 / 煞 / 大凶")
    trigram: str = Field("", description="该星所在之宫")
    direction: str = Field("", description="该宫方位，如「东南」")
    luoshu: int = Field(0, ge=0, le=9, description="该宫洛书数")
    meaning: str = Field("", description="星曜释义")
    suitable: list[str] = Field(default_factory=list, description="宜作何用")
    avoid: list[str] = Field(default_factory=list, description="忌作何用")
    is_base: bool = Field(False, description="是否伏位（本卦宫）")


class BazhaiCompat(BaseModel):
    """宅命匹配：东四命宜东四宅、西四命宜西四宅。"""

    matched: bool = False
    same_gua: bool = Field(False, description="命卦与宅卦同宫")
    level: str = Field("", description="同宫 / 相配 / 不配")
    score: int = Field(0, ge=0, le=100)
    ming_group: str = ""
    zhai_group: str = ""
    summary: str = ""
    advice: list[str] = Field(default_factory=list, description="调和路径")


class BazhaiRoom(BaseModel):
    """某功能房间的选位建议（按宅卦游年）。"""

    key: str = ""
    name: str = Field("", description="大门 / 卧室 / 厨房 / 卫生间 …")
    recommend: list[dict] = Field(default_factory=list, description="推荐方位，按优先级")
    avoid: list[dict] = Field(default_factory=list, description="忌用方位")
    headline: str = Field("", description="首选方位文案，如「东南 · 生气」")
    note: str = Field("", description="传统依据一句话")


class BazhaiDirections(BaseModel):
    """本命吉方：床位、书桌、办公位的朝向依据。"""

    lucky: list[dict] = Field(default_factory=list, description="本命四吉方")
    unlucky: list[dict] = Field(default_factory=list, description="本命四凶方")
    summary: str = ""
    bed: str = Field("", description="床位朝向建议")
    desk: str = Field("", description="书桌朝向建议")


class BazhaiResponse(BaseModel):
    """八宅盘：命卦 + 宅卦 + 游年八星 + 宅命匹配 + 房间选位。"""

    birth: BazhaiBirth
    ming_gua: MingGuaOut
    zhai_gua: ZhaiGuaOut
    compat: BazhaiCompat
    stars: list[BazhaiStar] = Field(
        default_factory=list, description="宅卦游年八星，自乾起顺时针 8 项"
    )
    auspicious: list[BazhaiStar] = Field(
        default_factory=list, description="四吉方，按吉次排序"
    )
    inauspicious: list[BazhaiStar] = Field(
        default_factory=list, description="四凶方，按凶重排序"
    )
    ming_stars: list[BazhaiStar] = Field(
        default_factory=list, description="命卦游年八星（个人吉方）"
    )
    ming_directions: BazhaiDirections
    rooms: list[BazhaiRoom] = Field(default_factory=list)
    key_points: list[str] = Field(default_factory=list, description="行动要点")
    rules_version: str = Field("", description="本次计算所采用的规则集版本")


# ---------------------------------------------------------------- 黄历 / 择日
class AlmanacLunar(BaseModel):
    """农历日期。"""

    text: str = Field("", description="完整农历串，如「二〇二六年九月初五」")
    year: str = ""
    month: str = Field("", description="含「月」字，如「九月」")
    day: str = Field("", description="如「初五」")
    is_leap: bool = Field(False, description="是否闰月")


class AlmanacGanZhi(BaseModel):
    """年月日干支与生肖。"""

    year: str = ""
    month: str = ""
    day: str = ""
    year_animal: str = ""
    month_animal: str = ""
    day_animal: str = ""


class AlmanacXun(BaseModel):
    """旬与旬空。"""

    name: str = Field("", description="日柱所在旬，如「甲寅」")
    kong: str = Field("", description="旬空二支，如「子丑」")


class AlmanacJianChu(BaseModel):
    """建除十二神。tone 为吉凶档：大吉 / 黄道 / 黑道 / 大凶。"""

    name: str = ""
    label: str = Field("", description="如「闭日」")
    tone: str = ""
    meaning: str = ""
    good: str = Field("", description="该日所宜")
    bad: str = Field("", description="该日所忌")
    motto: str = Field("", description="分档口诀，便于用户理解依据")


class AlmanacTianShen(BaseModel):
    """日家十二天神（黄道六神 / 黑道六神）。"""

    name: str = ""
    type: str = Field("", description="黄道 / 黑道")
    luck: str = Field("", description="吉 / 凶")
    meaning: str = ""


class AlmanacXiu(BaseModel):
    """二十八宿。"""

    name: str = ""
    full: str = Field("", description="全名，如「轸水蚓」")
    animal: str = Field("", description="宿主禽")
    mansion: str = Field("", description="所属四象，如「南方朱雀」")
    luck: str = Field("", description="吉 / 凶")


class AlmanacChong(BaseModel):
    """冲煞。"""

    zodiac: str = Field("", description="所冲生肖")
    desc: str = Field("", description="如「(乙卯)兔」")
    sha: str = Field("", description="煞方，如「东」")


class AlmanacPengZu(BaseModel):
    """彭祖百忌。"""

    gan: str = ""
    zhi: str = ""


class AlmanacGod(BaseModel):
    """五神方位之一。"""

    key: str = ""
    name: str = Field("", description="喜神 / 福神 / 财神 / 阳贵 / 阴贵")
    direction: str = ""


class AlmanacHour(BaseModel):
    """单个时辰的黄黑道与宜忌。

    子时按历法库拆为「早子时」（00:00-00:59）与「晚子时」（23:00-23:59），
    两者干支与吉凶不同，故一次返回 13 项而非 12 项，由 slot_label 区分。
    """

    index: int = 0
    branch: str = ""
    label: str = Field("", description="如「子时」")
    slot_label: str = Field("", description="如「子时（早）」")
    range: str = Field("", description="如「00:00–00:59」")
    gan_zhi: str = ""
    na_yin: str = ""
    tian_shen: str = ""
    tian_shen_type: str = Field("", description="黄道 / 黑道")
    luck: str = Field("", description="吉 / 凶")
    is_lucky: bool = False
    chong: dict = Field(default_factory=dict)
    cai_direction: str = Field("", description="该时辰财神方位")
    yi: list[str] = Field(default_factory=list)
    ji: list[str] = Field(default_factory=list)


class AlmanacPurpleWhite(BaseModel):
    """当日紫白（复用日家紫白引擎）。"""

    center_star: int = 0
    center_star_name: str = ""
    escape: str = ""
    escape_desc: str = ""
    yuan: str = ""
    # 与每日紫白盘同结构：best / worst 各是一个方位对象而非列表
    best: dict = Field(default_factory=dict, description="今日吉位")
    worst: dict = Field(default_factory=dict, description="今日忌方")
    calendar_exact: bool = Field(True, description="节气是否取自真实历法")


class AlmanacDay(BaseModel):
    """一日通书。"""

    date: str
    weekday: str = ""
    weekday_index: int = Field(0, ge=0, le=6)
    lunar: AlmanacLunar
    gan_zhi: AlmanacGanZhi
    xun: AlmanacXun
    solar_term: str = Field("", description="当日若交节则为节气名，否则空")
    solar_term_range: str = Field("", description="所处节气区间，如「寒露后 · 霜降前」")
    jian_chu: AlmanacJianChu
    tian_shen: AlmanacTianShen
    xiu: AlmanacXiu
    chong: AlmanacChong
    na_yin: str = ""
    yi: list[str] = Field(default_factory=list, description="宜（已剔除字面量「无」）")
    ji: list[str] = Field(default_factory=list, description="忌")
    all_avoid: bool = Field(False, description="忌项含「诸事不宜」")
    ji_shen: list[str] = Field(default_factory=list)
    xiong_sha: list[str] = Field(default_factory=list)
    peng_zu: AlmanacPengZu
    five_gods: list[AlmanacGod] = Field(default_factory=list)
    hours: list[AlmanacHour] = Field(default_factory=list, description="十三时辰")
    lucky_hours: list[AlmanacHour] = Field(default_factory=list)
    unlucky_hours: list[AlmanacHour] = Field(default_factory=list)
    purple_white: AlmanacPurpleWhite
    score: int = Field(0, ge=0, le=100, description="当日总体吉凶分（不含具体事项）")
    level: str = ""
    tone: str = ""
    score_reasons: list[str] = Field(default_factory=list, description="逐条打分依据")
    rules_version: str = ""


class AlmanacActivity(BaseModel):
    """可择日的事项。"""

    key: str
    name: str
    terms: list[str] = Field(default_factory=list)
    note: str = ""


class AlmanacLuckyHour(BaseModel):
    """择日结果中的可用吉时。"""

    label: str = ""
    range: str = ""
    tian_shen: str = ""
    gan_zhi: str = ""


class AlmanacPick(BaseModel):
    """择日结果的一条候选日。"""

    date: str
    weekday: str = ""
    lunar: str = ""
    gan_zhi: str = Field("", description="日干支")
    jian_chu: str = ""
    jian_chu_label: str = ""
    jian_chu_tone: str = ""
    tian_shen: str = ""
    tian_shen_type: str = ""
    xiu: str = ""
    xiu_luck: str = ""
    chong: AlmanacChong
    score: int = Field(0, ge=0, le=100)
    level: str = ""
    tone: str = ""
    hits: list[str] = Field(default_factory=list, description="命中的宜项")
    misses: list[str] = Field(default_factory=list, description="命中的忌项")
    reasons: list[str] = Field(default_factory=list, description="逐条打分依据")
    clash: bool = Field(False, description="是否冲用户生肖")
    lucky_hour_count: int = 0
    lucky_hours: list[AlmanacLuckyHour] = Field(default_factory=list)
    best_hour: str = ""


class AlmanacSelectRequest(BaseModel):
    """择日入参。"""

    activity: str = Field(..., min_length=1, description="事项 key，见 /almanac/activities")
    start_date: Optional[str] = Field(
        None, description="起始日期 YYYY-MM-DD；缺省为今天"
    )
    days: int = Field(30, ge=1, le=366, description="扫描天数")
    zodiac: Optional[str] = Field(
        None, max_length=2, description="用户生肖，用于避冲；留空则不避"
    )
    limit: int = Field(8, ge=1, le=60, description="返回候选条数")
    min_score: int = Field(0, ge=0, le=100, description="分数下限")


class AlmanacSelectRange(BaseModel):
    start: str = ""
    end: str = ""
    days: int = 0


class AlmanacSelectResponse(BaseModel):
    """择日结果。"""

    activity: AlmanacActivity
    range: AlmanacSelectRange
    zodiac: str = ""
    min_score: int = 0
    scanned: int = Field(0, description="实际扫描天数")
    recommended_count: int = Field(0, description="达标条数（可能大于 items 长度）")
    items: list[AlmanacPick] = Field(default_factory=list, description="按分数降序")
    best: Optional[AlmanacPick] = Field(None, description="区间内最高分的一天")
    rules_version: str = ""


class AlmanacCalendarDay(BaseModel):
    """月历中的单日。"""

    date: str
    day: int = 0
    weekday: str = ""
    lunar_day: str = ""
    score: int = Field(0, ge=0, le=100)
    level: str = ""
    tone: str = ""
    jian_chu: str = ""
    xiu: str = ""
    xiu_luck: str = ""
    chong: str = ""
    clash: bool = False
    lucky_hour_count: int = 0


class AlmanacCalendar(BaseModel):
    """整月每日吉凶（月历热力）。"""

    year: int
    month: int
    activity: Optional[dict] = Field(None, description="为空表示当日总体吉凶")
    zodiac: str = ""
    first_weekday: int = Field(0, ge=0, le=6, description="当月 1 日是周几，0=周一")
    days: list[AlmanacCalendarDay] = Field(default_factory=list)
    best: Optional[AlmanacCalendarDay] = None
    rules_version: str = ""


# ---------------------------------------------------------------- 玄空飞星 · 进阶
class XuankongStack(BaseModel):
    """月星与流年星同宫的复合结论。"""

    key: str = Field("", description="叠吉 / 小吉 / 参半 / 叠凶 / 重凶 / 五黄同宫 / 双五黄")
    level: str = Field("", description="旺 / 平 / 煞 / 大凶")
    note: str = ""


class XuankongMonthPalace(BaseModel):
    """玄空月盘的一宫：月星叠流年星。"""

    luoshu: int = Field(0, ge=0, le=9, description="洛书数，5 为中宫")
    key: str = Field("", description="方位，与前端九宫格映射键一致")
    trigram: str = ""
    direction: str = ""
    star: int = Field(0, ge=0, le=9, description="月星入中后飞临本宫之星")
    star_name: str = Field("", description="如「八白」")
    element: str = ""
    level: str = Field("", description="旺 / 平 / 煞 / 大凶")
    label: str = ""
    note: str = ""
    is_center: bool = False
    year_star: int = Field(0, ge=0, le=9, description="同宫流年星")
    year_star_name: str = ""
    year_star_level: str = ""
    stacked: bool = Field(
        False, description="月星与流年星同数同宫（两盘皆顺飞，故这要求入中之数相同）"
    )
    stack: XuankongStack


class XuankongExtreme(BaseModel):
    """月盘的最旺宫 / 最凶宫。"""

    direction: str = ""
    trigram: str = ""
    star: int = Field(0, ge=0, le=9, description="该宫月星之数")
    star_name: str = ""
    label: str = ""
    level: str = ""
    note: str = ""
    title: str = ""


class XuankongMonth(BaseModel):
    """玄空月盘：按节气月起飞星，并与流年盘叠看。"""

    date: str = ""
    year: int = 0
    branch: str = Field("", description="立春分界后的年支")
    month_index: int = Field(0, ge=0, le=12, description="节气月序，1 起")
    month_name: str = Field("", description="如「九月」")
    jieqi: str = Field("", description="本月的「节」，如「寒露」")
    jieqi_mnemonic: str = ""
    center_star: int = Field(0, ge=0, le=9, description="月星入中之数")
    center_star_name: str = ""
    year_center_star: int = Field(0, ge=0, le=9, description="流年星入中之数")
    year_center_star_name: str = ""
    palaces: list[XuankongMonthPalace] = Field(default_factory=list)
    best: XuankongExtreme
    worst: XuankongExtreme
    key_points: list[str] = Field(default_factory=list)
    rules_version: str = ""


class XuankongStarState(BaseModel):
    """某星在当运下的旺衰（玄空论吉凶看的是与当运的关系）。"""

    state: str = Field("", description="旺 / 生 / 退 / 死 / 煞")
    level: str = Field("", description="旺 / 平 / 煞 / 大凶")
    note: str = ""
    delta: int = Field(0, ge=0, le=8, description="该星距当运星的偏移")
    is_wang: bool = Field(False, description="是否为当运旺星")


class XuankongHousePalace(BaseModel):
    """宅运盘的一宫：山星 / 运星 / 向星三盘叠加。"""

    luoshu: int = Field(0, ge=0, le=9)
    key: str = ""
    trigram: str = ""
    direction: str = ""
    is_center: bool = False
    shan_star: int = Field(0, ge=0, le=9, description="山星（管人丁健康）")
    shan_star_name: str = ""
    yun_star: int = Field(0, ge=0, le=9, description="运星（主该宫时运）")
    yun_star_name: str = ""
    xiang_star: int = Field(0, ge=0, le=9, description="向星（管财禄事业）")
    xiang_star_name: str = ""
    shan_state: XuankongStarState
    xiang_state: XuankongStarState
    yun_state: XuankongStarState
    level: str = Field("", description="本宫综合吉凶，复用四档值域")
    role: str = Field("", description="本宫宜作何用")
    has_lost_wuhuang: bool = Field(False, description="本宫有失运五黄")
    is_sit: bool = Field(False, description="是否为坐山宫")
    is_face: bool = Field(False, description="是否为向首宫")


class XuankongSide(BaseModel):
    """坐山 / 向首。"""

    mountain: str = Field("", description="山名，如「子」")
    trigram: str = ""
    direction: str = ""
    luoshu: int = Field(0, ge=0, le=9)
    dragon: str = Field("", description="三元龙：天元 / 地元 / 人元")
    yin_yang: str = Field("", description="阴 / 阳")
    degree: Optional[float] = None
    offset: Optional[float] = Field(
        None, description="偏离该山中心线的角度，用于兼向提示"
    )
    label: str = Field("", description="如「子（天元龙 · 阴）」")


class XuankongYun(BaseModel):
    """三元九运。"""

    number: int = Field(0, ge=0, le=9)
    name: str = Field("", description="如「九运」")
    yuan: str = Field("", description="上元 / 中元 / 下元")
    element: str = ""
    star: int = Field(0, ge=0, le=9, description="当运星，即旺星")
    star_name: str = ""
    start_year: int = 0
    end_year: int = 0
    source: str = Field("", description="year / build_year / explicit")
    label: str = ""
    summary: str = ""


class XuankongCenter(BaseModel):
    """中宫：山星、向星的入中之数及顺逆判据。"""

    shan_star: int = Field(0, ge=0, le=9, description="山星入中之数")
    shan_forward: bool = False
    xiang_star: int = Field(0, ge=0, le=9, description="向星入中之数")
    xiang_forward: bool = False
    shan_direction: str = Field("", description="顺飞 / 逆飞")
    xiang_direction: str = ""
    shan_basis: str = Field("", description="山星顺逆的判据说明，便于用户追溯")
    xiang_basis: str = ""


class XuankongPattern(BaseModel):
    """宅运格局：旺山旺向 / 双星会向 / 双星会坐 / 上山下水 / 到山 / 到向 / 两不到。"""

    key: str = ""
    name: str = ""
    level: str = Field("", description="旺 / 平 / 煞 / 大凶")
    summary: str = ""
    advice: str = ""
    to_sit: bool = Field(False, description="山盘旺星到坐山")
    to_face: bool = Field(False, description="向盘旺星到向首")
    shan_at_sit: bool = False
    shan_at_face: bool = False
    xiang_at_sit: bool = False
    xiang_at_face: bool = False


class XuankongRole(BaseModel):
    """三盘的职责说明。"""

    name: str = ""
    duty: str = ""
    good: str = ""
    bad: str = ""


class XuankongHouseRequest(BaseModel):
    """宅运盘入参：坐向（度数或宅卦）+ 元运（运数或建宅年份）。

    坐向二者取一：给 ``degree``（罗盘读数）最准，会一并返回坐向明细与兼向提示；
    只知卦时传 ``trigram``，此时取该卦的**天元龙**为坐山。
    元运二者取一：``yun`` 直接指定运数；``build_year`` 由建宅年份自动推算，
    两者都给时以 ``yun`` 为准。
    """

    degree: Optional[float] = Field(
        None, ge=0, lt=360, description="罗盘读到的坐山方位角；为空则用 trigram"
    )
    declination: float = Field(0.0, ge=-30, le=30, description="当地磁偏角")
    trigram: str = Field(
        "", max_length=4, description="直接指定坐山卦，如「坎」；degree 为空时使用"
    )
    yun: Optional[int] = Field(
        None, ge=1, le=9, description="当运之数 1-9；为空则由 build_year 推算"
    )
    build_year: Optional[int] = Field(
        None, ge=1864, le=2100, description="建宅 / 入宅年份，用于自动定元运"
    )
    name: str = Field("", max_length=30, description="名称（可选，仅作回显）")


class XuankongHouse(BaseModel):
    """宅运盘：三盘叠加 + 格局判定 + 逐宫吉凶。"""

    name: str = ""
    title: str = Field("", description="如「子山午向 · 九运宅运盘」")
    sit: XuankongSide
    face: XuankongSide
    orientation: dict = Field(default_factory=dict, description="坐向明细（走度数时才有）")
    yun: XuankongYun
    center: XuankongCenter
    palaces: list[XuankongHousePalace] = Field(default_factory=list)
    pattern: XuankongPattern
    score: int = Field(0, ge=0, le=100)
    level: str = Field("", description="上吉 / 吉 / 平 / 欠佳 / 凶")
    level_key: str = Field("", description="四档吉凶，驱动前端配色")
    jianxiang: bool = Field(False, description="坐向偏离中心较多，已属兼向")
    roles: dict[str, XuankongRole] = Field(
        default_factory=dict, description="山星 / 向星 / 运星的职责说明"
    )
    key_points: list[str] = Field(default_factory=list)
    rules_version: str = ""
