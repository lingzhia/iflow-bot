"""配置 schema for iflow-bot。

参考: https://platform.iflow.cn/cli/configuration/settings
"""

from pathlib import Path
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


# ============================================================================
# 渠道配置
# ============================================================================

class TelegramConfig(BaseModel):
    model_config = {"extra": "ignore"}
    
    enabled: bool = False
    token: str = ""
    allow_from: list[str] = Field(default_factory=list)


class DiscordConfig(BaseModel):
    model_config = {"extra": "ignore"}
    
    enabled: bool = False
    token: str = ""
    allow_from: list[str] = Field(default_factory=list)


class WhatsAppConfig(BaseModel):
    model_config = {"extra": "ignore"}
    
    enabled: bool = False
    bridge_url: str = "http://localhost:3001"
    bridge_token: str = ""
    allow_from: list[str] = Field(default_factory=list)


class FeishuConfig(BaseModel):
    model_config = {"extra": "ignore"}
    
    enabled: bool = False
    app_id: str = ""
    app_secret: str = ""
    encrypt_key: str = ""
    verification_token: str = ""
    allow_from: list[str] = Field(default_factory=list)


class SlackConfig(BaseModel):
    model_config = {"extra": "ignore"}

    class DMConfig(BaseModel):
        model_config = {"extra": "ignore"}

        enabled: bool = True
        policy: Literal["open", "allowlist"] = "open"
        allow_from: list[str] = Field(default_factory=list)

    enabled: bool = False
    bot_token: str = ""
    app_token: str = ""
    allow_from: list[str] = Field(default_factory=list)
    group_policy: Literal["mention", "open", "allowlist"] = "mention"
    group_allow_from: list[str] = Field(default_factory=list)
    reply_in_thread: bool = True
    react_emoji: str = "eyes"
    dm: DMConfig = Field(default_factory=DMConfig)


class DingTalkConfig(BaseModel):
    model_config = {"extra": "ignore"}
    
    enabled: bool = False
    client_id: str = ""
    client_secret: str = ""
    robot_code: str = ""  # 机器人代码（群聊需要）
    card_template_id: str = ""  # AI Card 模板 ID（流式输出需要）
    card_template_key: str = "content"  # AI Card 内容字段名
    allow_from: list[str] = Field(default_factory=list)


class QQConfig(BaseModel):
    model_config = {"extra": "ignore"}
    
    enabled: bool = False
    app_id: str = ""
    secret: str = ""
    allow_from: list[str] = Field(default_factory=list)
    split_threshold: int = 3
    """流式分段发送阈值（基于换行符数量）。

    - 0: 不分段，等 AI 全部输出完后一次性发送
    - N > 0: 流式接收时每累积 N 个换行符立即推送一条新 QQ 消息，剩余内容在结束时补发
    """


class EmailConfig(BaseModel):
    model_config = {"extra": "ignore"}
    
    enabled: bool = False
    consent_granted: bool = False
    imap_host: str = ""
    imap_port: int = 993
    imap_username: str = ""
    imap_password: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    from_address: str = ""
    allow_from: list[str] = Field(default_factory=list)
    auto_reply_enabled: bool = True


class MochatConfig(BaseModel):
    model_config = {"extra": "ignore"}
    
    enabled: bool = False
    base_url: str = "https://mochat.io"
    socket_url: str = "https://mochat.io"
    socket_path: str = "/socket.io"
    claw_token: str = ""
    agent_user_id: str = ""
    sessions: list[str] = Field(default_factory=lambda: ["*"])
    panels: list[str] = Field(default_factory=lambda: ["*"])


class WechatWorkConfig(BaseModel):
    """企业微信配置。
    
    支持两种模式：
    1. 应用机器人：通过企业微信 API 接收和发送消息
    2. 群机器人：通过 Webhook 发送消息（仅发送）
    """
    model_config = {"extra": "ignore"}
    
    enabled: bool = False
    
    # 企业 ID
    corp_id: str = ""
    
    # 应用配置
    agent_id: str = ""  # 应用 AgentId
    secret: str = ""    # 应用 Secret
    
    # 回调配置（可选，用于消息验证和加解密）
    token: str = ""
    encoding_aes_key: str = ""
    
    # 内嵌 HTTP 服务配置（Gateway 模式）
    callback_port: int = 8788
    """内嵌 HTTP 回调服务端口。"""
    
    callback_host: str = "0.0.0.0"
    """内嵌 HTTP 回调服务监听地址。"""
    
    # 消息接收模式
    stream_mode: bool = False
    """是否启用 Stream Mode（长轮询）。
    
    False: 回调模式，Gateway 会启动内嵌 HTTP 服务接收回调
    True: 轮询模式，自动拉取消息（需要中间服务支持）
    """
    
    poll_interval: int = 5
    """轮询间隔（秒），仅 stream_mode=True 时有效。"""
    
    # 权限控制
    allow_from: list[str] = Field(default_factory=list)
    """允许的用户 ID 白名单。
    
    - 空列表: 允许所有用户
    - 非空: 只允许列表中的用户 ID
    """
    
    # 群聊配置
    group_policy: str = "mention"
    """群聊消息响应策略。
    
    - "mention": 只响应 @机器人 的消息
    - "open": 响应所有群消息
    - "allowlist": 只响应白名单群的消息
    """
    
    group_allow_from: list[str] = Field(default_factory=list)
    """群聊白名单，仅 group_policy="allowlist" 时有效。"""
    
    # Webhook 配置（群机器人）
    webhook_url: str = ""
    """群机器人 Webhook URL（可选）。
    
    配置后可通过 send_webhook 方法发送消息到指定群。
    """


class ChannelsConfig(BaseModel):
    model_config = {"extra": "ignore"}
    
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    discord: DiscordConfig = Field(default_factory=DiscordConfig)
    whatsapp: WhatsAppConfig = Field(default_factory=WhatsAppConfig)
    feishu: FeishuConfig = Field(default_factory=FeishuConfig)
    slack: SlackConfig = Field(default_factory=SlackConfig)
    dingtalk: DingTalkConfig = Field(default_factory=DingTalkConfig)
    qq: QQConfig = Field(default_factory=QQConfig)
    email: EmailConfig = Field(default_factory=EmailConfig)
    mochat: MochatConfig = Field(default_factory=MochatConfig)
    wechat_work: WechatWorkConfig = Field(default_factory=WechatWorkConfig)
    
    send_progress: bool = True
    send_tool_hints: bool = True


# ============================================================================
# Driver 配置（iflow 设置）
# ============================================================================

class DriverConfig(BaseModel):
    """IFlow driver 配置。
    
    参考: https://platform.iflow.cn/cli/configuration/settings
    """
    model_config = {"extra": "ignore"}
    
    mode: Literal["cli", "acp", "stdio"] = "stdio"
    """通信模式: cli (子进程调用), acp (WebSocket), 或 stdio (直接通过 stdin/stdout)"""
    
    iflow_path: str = "iflow"
    model: str = "GLM-5"
    yolo: bool = True
    thinking: bool = False
    max_turns: int = 40
    timeout: int = 1200
    compression_trigger_tokens: int = 88888
    """活跃会话自动压缩触发阈值（估算 token）"""
    workspace: str = ""  # 关键：iflow 工作目录
    extra_args: list[str] = Field(default_factory=list)
    
    # ACP 模式配置
    acp_port: int = 8090
    """ACP 模式下的端口号"""
    
    acp_host: str = "localhost"
    """ACP 模式下的主机地址"""


# ============================================================================
# 主配置
# ============================================================================

class Config(BaseSettings):
    """iflow-bot 主配置。

    配置统一放在 driver 下，避免重复字段。
    """

    model_config = {
        "env_prefix": "IFLOW_BOT_",
        "env_nested_delimiter": "__",
        "extra": "ignore",
    }

    # 工作目录（优先级高于 driver.workspace）
    workspace: Optional[str] = None

    # Driver 配置（包含 model, workspace, timeout 等）
    driver: DriverConfig = Field(default_factory=DriverConfig)

    # 渠道配置
    channels: ChannelsConfig = Field(default_factory=ChannelsConfig)

    # 日志
    log_level: str = "INFO"
    log_file: str = ""

    def get_enabled_channels(self) -> list[str]:
        """获取已启用的渠道列表。"""
        enabled = []
        for name in ["telegram", "discord", "whatsapp", "feishu", "slack",
                     "dingtalk", "qq", "email", "mochat", "wechat_work"]:
            channel = getattr(self.channels, name, None)
            if channel and getattr(channel, "enabled", False):
                enabled.append(name)
        return enabled

    def get_workspace(self) -> str:
        """获取 workspace 路径。

        优先使用顶层 workspace 字段，其次使用 driver.workspace，默认为 ~/.iflow-bot/workspace
        """
        # 优先使用顶层 workspace 字段
        if hasattr(self, 'workspace') and self.workspace:
            return self.workspace
        # 其次使用 driver.workspace
        if self.driver and self.driver.workspace:
            return self.driver.workspace
        # 默认值
        return str(Path.home() / ".iflow-bot" / "workspace")

    def get_model(self) -> str:
        """获取模型名称。

        优先使用 driver.model，默认为 glm-5
        """
        if self.driver and self.driver.model:
            return self.driver.model
        return "glm-5"

    def get_timeout(self) -> int:
        """获取超时时间。"""
        if self.driver and self.driver.timeout:
            return self.driver.timeout
        return 1200
