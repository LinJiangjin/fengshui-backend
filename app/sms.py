# -*- coding: utf-8 -*-
"""短信发送：可插拔 provider。

当前支持两种：
- console  开发默认。验证码只写服务端日志，不发真实短信，零成本联调。
- aliyun   阿里云短信。需要额外安装官方 SDK 并在 .env 配置密钥与模板。

切换方式：在 server/.env 里设置
    SMS_PROVIDER=aliyun
    ALIYUN_SMS_ACCESS_KEY_ID=...
    ALIYUN_SMS_ACCESS_KEY_SECRET=...
    ALIYUN_SMS_SIGN_NAME=...
    ALIYUN_SMS_TEMPLATE_CODE=...

新增服务商（腾讯云等）只需实现 `SmsProvider` 协议并在这里注册，
路由层不感知具体实现。
"""

from typing import Protocol

from .config import (
    ALIYUN_SMS_ACCESS_KEY_ID,
    ALIYUN_SMS_ACCESS_KEY_SECRET,
    ALIYUN_SMS_SIGN_NAME,
    ALIYUN_SMS_TEMPLATE_CODE,
    SMS_PROVIDER,
)


class SmsSendError(RuntimeError):
    """短信发送失败。路由层捕获后返回可读错误，不泄底层细节。"""


class SmsProvider(Protocol):
    """短信服务商协议。"""

    name: str

    def send(self, phone: str, code: str, scene: str) -> None:
        """发送验证码；失败时抛 `SmsSendError`。"""
        ...


class ConsoleSmsProvider:
    """开发用：验证码只打印到服务端日志，不产生任何外部调用。"""

    name = "console"

    def send(self, phone: str, code: str, scene: str) -> None:
        print(f"[sms:console] scene={scene} phone={phone} code={code}")


class AliyunSmsProvider:
    """阿里云短信。

    需要 `pip install alibabacloud_dysmsapi20170525`。
    SDK 采用懒加载：没装 SDK 时只有在真正发短信的那一刻才会报错，
    不影响 console 模式下的开发与测试。
    """

    name = "aliyun"

    def __init__(self) -> None:
        missing = [
            key
            for key, value in (
                ("ALIYUN_SMS_ACCESS_KEY_ID", ALIYUN_SMS_ACCESS_KEY_ID),
                ("ALIYUN_SMS_ACCESS_KEY_SECRET", ALIYUN_SMS_ACCESS_KEY_SECRET),
                ("ALIYUN_SMS_SIGN_NAME", ALIYUN_SMS_SIGN_NAME),
                ("ALIYUN_SMS_TEMPLATE_CODE", ALIYUN_SMS_TEMPLATE_CODE),
            )
            if not value
        ]
        if missing:
            raise SmsSendError(
                "阿里云短信配置缺失：" + "、".join(missing) + "，请在 server/.env 中补全"
            )
        self._client = None

    def _ensure_client(self):
        if self._client is not None:
            return self._client
        try:
            from alibabacloud_dysmsapi20170525.client import Client
            from alibabacloud_tea_openapi import models as open_api_models
        except ImportError as exc:  # SDK 未安装
            raise SmsSendError(
                "未安装阿里云短信 SDK，请执行："
                "pip install alibabacloud_dysmsapi20170525"
            ) from exc

        config = open_api_models.Config(
            access_key_id=ALIYUN_SMS_ACCESS_KEY_ID,
            access_key_secret=ALIYUN_SMS_ACCESS_KEY_SECRET,
        )
        config.endpoint = "dysmsapi.aliyuncs.com"
        self._client = Client(config)
        return self._client

    def send(self, phone: str, code: str, scene: str) -> None:
        from alibabacloud_dysmsapi20170525 import models as dysms_models

        client = self._ensure_client()
        request = dysms_models.SendSmsRequest(
            phone_numbers=phone,
            sign_name=ALIYUN_SMS_SIGN_NAME,
            template_code=ALIYUN_SMS_TEMPLATE_CODE,
            template_param=f'{{"code":"{code}"}}',
        )
        try:
            response = client.send_sms(request)
        except Exception as exc:  # 网络 / 鉴权失败
            raise SmsSendError(f"阿里云短信发送异常：{exc}") from exc

        body = getattr(response, "body", None)
        if body is None or getattr(body, "code", None) != "OK":
            detail = getattr(body, "message", "未知错误") if body else "无响应"
            raise SmsSendError(f"阿里云短信发送失败：{detail}")


_PROVIDERS: dict[str, type] = {
    "console": ConsoleSmsProvider,
    "aliyun": AliyunSmsProvider,
}


def get_sms_provider() -> SmsProvider:
    """按配置实例化短信服务商。配置写错时明确报错，不静默降级。"""
    provider_cls = _PROVIDERS.get(SMS_PROVIDER)
    if provider_cls is None:
        raise SmsSendError(
            f"未知的 SMS_PROVIDER={SMS_PROVIDER}，可选：{'、'.join(_PROVIDERS)}"
        )
    return provider_cls()  # type: ignore[return-value]
