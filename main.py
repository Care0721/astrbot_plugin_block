"""
astrbot_plugin_guardian — Bot守护者插件
保护 Monika（或自定义Bot名）免受辱骂，自动检测、拉黑、通知。
适配 AstrBot 4.24.x
"""

import json
import os
import re
import smtplib
from datetime import datetime
from difflib import SequenceMatcher
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from astrbot.api import logger
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Star, register, Context


@register(
    name="astrbot_plugin_guardian",
    desc="Bot守护者 - 全天监测辱骂行为，自动拉黑并邮件通知",
    version="1.1.0",
    author="Guardian"
)
class GuardianPlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context, config)

        # ── 数据持久化 ──────────────────────────────────────────
        self.data_file = os.path.join(os.path.dirname(__file__), "guardian_data.json")
        self.data = self._load_data()

        # ── 读取配置 ────────────────────────────────────────────
        self.bot_name          = config.get("bot_name", "Monika")
        self.default_keywords  = config.get("keywords", [
            "傻逼", "废物", "滚", "垃圾", "蠢货", "sb", "草你", "操你",
            "fuck you", "笨蛋", "白痴", "去死", "死bot", "烂bot", "废bot",
            "垃圾bot", "蠢bot", "shit", "bastard", "idiot"
        ])
        self.fuzzy_threshold   = float(config.get("fuzzy_threshold", 0.75))
        self.admin_email       = config.get("admin_email", "carenb666@foxmail.com")
        self.sender_email      = config.get("qq_email", "")
        self.sender_auth_code  = config.get("qq_email_auth_code", "")
        self.auto_mute         = bool(config.get("auto_mute", True))
        self.mute_duration     = int(config.get("mute_duration", 2592000))  # 默认30天
        self.auto_kick         = bool(config.get("auto_kick", False))

        # ── 启动日志 ────────────────────────────────────────────
        logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        logger.info(" Guardian 守护插件 已加载 ✅")
        logger.info(f" 保护目标   : {self.bot_name}")
        logger.info(f" 黑名单人数 : {len(self.data['blacklist'])} 人")
        logger.info(f" 自定义关键词: {len(self.data.get('custom_keywords', []))} 个")
        logger.info(f" 自动禁言   : {'开启' if self.auto_mute else '关闭'}")
        logger.info(f" 自动踢出   : {'开启' if self.auto_kick else '关闭'}")
        logger.info(f" 邮件通知   : {'已配置' if self.sender_email else '未配置（请在设置中填写QQ邮箱）'}")
        logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    # ────────────────────────────────────────────────────────────
    # 数据持久化
    # ────────────────────────────────────────────────────────────

    def _load_data(self) -> dict:
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"[Guardian] 数据文件读取失败: {e}")
        return {"blacklist": {}, "custom_keywords": []}

    def _save_data(self):
        try:
            with open(self.data_file, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"[Guardian] 数据保存失败: {e}")

    # ────────────────────────────────────────────────────────────
    # 黑名单操作
    # ────────────────────────────────────────────────────────────

    def _is_blacklisted(self, user_id: str) -> bool:
        return str(user_id) in self.data["blacklist"]

    def _add_to_blacklist(self, user_id: str, reason: str = "", group_id: str = ""):
        uid = str(user_id)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.data["blacklist"][uid] = {
            "reason": reason,
            "time": now,
            "group_id": str(group_id)
        }
        self._save_data()
        # 控制台高亮输出
        logger.warning("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        logger.warning(f" [Guardian] 🚫 新增黑名单用户")
        logger.warning(f"  QQ号  : {uid}")
        logger.warning(f"  原因  : {reason[:80]}")
        logger.warning(f"  群组  : {group_id or '未知'}")
        logger.warning(f"  时间  : {now}")
        logger.warning("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        self._print_blacklist_summary()

    def _remove_from_blacklist(self, user_id: str) -> bool:
        uid = str(user_id)
        if uid in self.data["blacklist"]:
            del self.data["blacklist"][uid]
            self._save_data()
            logger.info(f"[Guardian] ✅ 用户 {uid} 已解除黑名单")
            self._print_blacklist_summary()
            return True
        return False

    def _print_blacklist_summary(self):
        """在控制台打印完整黑名单，方便管理员查看"""
        bl = self.data["blacklist"]
        logger.info("━━━━━ [Guardian] 当前黑名单一览 ━━━━━")
        if not bl:
            logger.info("  （黑名单为空）")
        else:
            for i, (uid, info) in enumerate(bl.items(), 1):
                logger.info(
                    f"  {i:>2}. QQ:{uid}  "
                    f"时间:{info.get('time','?')}  "
                    f"群:{info.get('group_id','?')}  "
                    f"原因:{info.get('reason','?')[:35]}"
                )
        logger.info(f"  共 {len(bl)} 人被拉黑")
        logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    # ────────────────────────────────────────────────────────────
    # 关键词检测
    # ────────────────────────────────────────────────────────────

    def _all_keywords(self) -> list:
        return self.default_keywords + self.data.get("custom_keywords", [])

    def _fuzzy_match(self, text: str, keyword: str) -> bool:
        """多策略模糊匹配，防止空格/谐音绕过"""
        t = text.lower()
        k = keyword.lower()

        # 1. 直接包含
        if k in t:
            return True

        # 2. 去空格匹配（防 "傻 逼" 绕过）
        t_ns = re.sub(r'\s+', '', t)
        k_ns = re.sub(r'\s+', '', k)
        if k_ns in t_ns:
            return True

        # 3. 滑动窗口相似度（捕捉谐音/近似词）
        w = max(len(k), 2)
        for i in range(max(len(t) - w + 1, 1)):
            chunk = t[i:i + w]
            if SequenceMatcher(None, chunk, k).ratio() >= self.fuzzy_threshold:
                return True

        return False

    def _detect_insult(self, text: str) -> Optional[str]:
        """返回首个匹配的关键词，未命中返回 None"""
        for kw in self._all_keywords():
            if self._fuzzy_match(text, kw):
                return kw
        return None

    def _mentions_bot(self, text: str) -> bool:
        return self.bot_name.lower() in text.lower()

    # ────────────────────────────────────────────────────────────
    # 从 event 提取 QQ 元数据
    # ────────────────────────────────────────────────────────────

    def _get_group_id(self, event: AstrMessageEvent) -> Optional[str]:
        """兼容多种 adapter 获取群ID"""
        # 方法1: message_obj 直属属性
        try:
            msg = event.message_obj
            for attr in ("group_id", "chat_id"):
                val = getattr(msg, attr, None)
                if val:
                    return str(val)
        except Exception:
            pass

        # 方法2: session_id 包含数字片段（如 group_12345678）
        try:
            sid = event.session_id or ""
            parts = re.findall(r'\d{5,}', sid)
            if parts:
                return parts[0]
        except Exception:
            pass

        # 方法3: unified_msg_origin
        try:
            origin = str(event.unified_msg_origin)
            parts = re.findall(r'\d{5,}', origin)
            if parts:
                return parts[0]
        except Exception:
            pass

        return None

    def _is_group(self, event: AstrMessageEvent) -> bool:
        try:
            origin = str(event.unified_msg_origin).lower()
            return "group" in origin
        except Exception:
            return self._get_group_id(event) is not None

    def _is_at_bot(self, event: AstrMessageEvent) -> bool:
        # AstrBot 内置 at_me 属性
        try:
            if hasattr(event, "is_at_me") and callable(event.is_at_me):
                return event.is_at_me()
        except Exception:
            pass
        # 备用：检查 message 段落中的 at 组件
        try:
            for seg in event.message_obj.message:
                if getattr(seg, "type", "") == "at":
                    return True
        except Exception:
            pass
        return False

    # ────────────────────────────────────────────────────────────
    # 调用 OneBot / QQ API
    # ────────────────────────────────────────────────────────────

    async def _onebot_call(self, event: AstrMessageEvent, action: str, **kwargs) -> bool:
        """向底层 OneBot adapter 发送 API 请求"""
        try:
            # NakuruProject / aiocqhttp 均通过 event.bot.api.call_action
            bot = event.bot
            if hasattr(bot, "api") and hasattr(bot.api, "call_action"):
                await bot.api.call_action(action, **kwargs)
                return True
        except Exception as e:
            logger.error(f"[Guardian] OneBot API [{action}] 调用失败: {e}")
        return False

    async def _execute_block(
        self,
        event: AstrMessageEvent,
        user_id: str,
        group_id: str,
        reason: str
    ):
        """执行全套拉黑流程"""
        uid_int = int(user_id) if user_id.isdigit() else 0
        gid_int = int(group_id) if group_id and group_id.isdigit() else 0

        # 1. 群禁言
        if self.auto_mute and gid_int and uid_int:
            ok = await self._onebot_call(
                event, "set_group_ban",
                group_id=gid_int,
                user_id=uid_int,
                duration=self.mute_duration
            )
            logger.info(f"[Guardian] 禁言 {user_id} {'✅' if ok else '❌（权限不足或非群消息）'}")

        # 2. 踢出群聊（可选）
        if self.auto_kick and gid_int and uid_int:
            ok = await self._onebot_call(
                event, "set_group_kick",
                group_id=gid_int,
                user_id=uid_int,
                reject_add_request=True
            )
            logger.info(f"[Guardian] 踢出 {user_id} {'✅' if ok else '❌（权限不足）'}")

        # 3. 写入内部黑名单（核心）
        self._add_to_blacklist(user_id, reason, group_id)

        # 4. 邮件通知被拉黑者
        await self._send_block_email(user_id)

    # ────────────────────────────────────────────────────────────
    # 邮件通知
    # ────────────────────────────────────────────────────────────

    async def _send_block_email(self, user_qq: str):
        if not self.sender_email or not self.sender_auth_code:
            logger.warning("[Guardian] ⚠️  QQ邮箱未配置，跳过发送邮件")
            return

        to_addr = f"{user_qq}@qq.com"
        subject = f"【{self.bot_name}】您已被列入黑名单通知"
        body = (
            f"您好，\n\n"
            f"您的 QQ 账号（{user_qq}）因在聊天中存在辱骂 {self.bot_name} 的行为，\n"
            f"已被管理系统自动拉入黑名单。\n\n"
            f"━━━ 处理详情 ━━━\n"
            f"状态     ：已拉黑 🚫\n"
            f"影响范围 ：{self.bot_name} 所有功能已对您全部禁用\n"
            f"生效时间 ：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"━━━ 如何申诉 ━━━\n"
            f"如您认为此处理有误，请发送邮件至管理员邮箱申请解除：\n"
            f"  {self.admin_email}\n\n"
            f"申诉时请说明您的 QQ 号及理由，管理员将在审核后处理。\n\n"
            f"━━━ 温馨提示 ━━━\n"
            f"请文明使用 AI 助手，共同维护良好的交流环境。\n\n"
            f"此致\n{self.bot_name} 管理系统\n{datetime.now().strftime('%Y年%m月%d日')}"
        )

        try:
            msg = MIMEMultipart("alternative")
            msg["From"]    = self.sender_email
            msg["To"]      = to_addr
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "plain", "utf-8"))

            with smtplib.SMTP_SSL("smtp.qq.com", 465, timeout=15) as server:
                server.login(self.sender_email, self.sender_auth_code)
                server.send_message(msg)

            logger.info(f"[Guardian] 📧 黑名单通知邮件已发送 → {to_addr}")
        except Exception as e:
            logger.error(f"[Guardian] 📧 邮件发送失败: {e}")

    # ────────────────────────────────────────────────────────────
    # ★ 核心事件监听：全消息拦截
    # ────────────────────────────────────────────────────────────

    @filter.event_message_create
    async def on_message(self, event: AstrMessageEvent):
        """
        监听所有进入 AstrBot 的消息（群聊 + 私聊）：
          ① 黑名单用户 → 拦截并提示
          ② 群聊辱骂（@bot 或 普通消息）→ 拉黑处理
        """
        try:
            text     = (event.get_plain_text() or event.message_str or "").strip()
            user_id  = str(event.get_sender_id())
            group_id = self._get_group_id(event) or ""
            is_group = self._is_group(event)

            # 忽略空消息和自身命令（避免与 /guardian 命令重复处理）
            if not text or text.lower().startswith("/guardian"):
                return

            # ── ① 黑名单拦截 ───────────────────────────────────
            if self._is_blacklisted(user_id):
                info = self.data["blacklist"][user_id]
                yield event.plain_result(
                    f"⛔ 您已被列入 {self.bot_name} 的黑名单，所有功能已全部禁用。\n"
                    f"  拉黑时间：{info.get('time', '未知')}\n"
                    f"  如需申请解除，请联系管理员：{self.admin_email}"
                )
                return  # 阻断后续 LLM 处理

            # ── ② 辱骂检测（仅群聊） ───────────────────────────
            if not is_group:
                return

            matched_kw = self._detect_insult(text)
            if not matched_kw:
                return

            is_at  = self._is_at_bot(event)
            reason = ""

            if is_at:
                # 场景A：用户 @bot 时辱骂
                reason = f"@机器人时辱骂（命中关键词「{matched_kw}」）：{text[:80]}"
            else:
                # 场景B：普通群消息中包含辱骂（不论是否提到bot名字）
                reason = f"群聊中辱骂（命中关键词「{matched_kw}」）：{text[:80]}"

            logger.warning(
                f"[Guardian] ⚠️  辱骂检测触发 | "
                f"用户:{user_id} | 群:{group_id} | "
                f"@bot:{is_at} | 关键词:「{matched_kw}」"
            )

            # 执行拉黑
            await self._execute_block(event, user_id, group_id, reason)

            yield event.plain_result(
                f"🚫 检测到辱骂 {self.bot_name} 的行为（关键词：{matched_kw}），\n"
                f"用户 {user_id} 已被自动拉黑，相关通知已发送至该用户邮箱。"
            )

        except Exception as e:
            logger.error(f"[Guardian] on_message 异常: {e}", exc_info=True)

    # ────────────────────────────────────────────────────────────
    # ★ 管理命令：/guardian
    # ────────────────────────────────────────────────────────────

    @filter.command("guardian")
    async def guardian_cmd(self, event: AstrMessageEvent):
        """
        Guardian 管理命令（建议仅管理员使用）
        用法见 /guardian help
        """
        raw   = (event.message_str or "").strip()
        # 提取 /guardian 之后的参数
        match = re.search(r'guardian\s*(.*)', raw, re.IGNORECASE)
        arg_str = match.group(1).strip() if match else ""
        parts   = arg_str.split() if arg_str else []

        if not parts:
            yield event.plain_result(self._help_text())
            return

        sub = parts[0].lower()

        # ── 查看黑名单 ──────────────────────────────────────
        if sub == "list":
            self._print_blacklist_summary()          # 控制台也刷新一次
            yield event.plain_result(self._blacklist_text())

        # ── 解除黑名单 ──────────────────────────────────────
        elif sub == "unblock":
            if len(parts) < 2:
                yield event.plain_result("❌ 用法：/guardian unblock <QQ号>")
                return
            uid = parts[1]
            if self._remove_from_blacklist(uid):
                yield event.plain_result(f"✅ 用户 {uid} 已从黑名单移除")
            else:
                yield event.plain_result(f"❌ 用户 {uid} 不在黑名单中")

        # ── 手动拉黑 ────────────────────────────────────────
        elif sub == "block":
            if len(parts) < 2:
                yield event.plain_result("❌ 用法：/guardian block <QQ号> [原因]")
                return
            uid    = parts[1]
            reason = " ".join(parts[2:]) if len(parts) > 2 else "管理员手动添加"
            self._add_to_blacklist(uid, reason, "手动")
            await self._send_block_email(uid)
            yield event.plain_result(
                f"✅ 用户 {uid} 已手动加入黑名单\n"
                f"原因：{reason}\n"
                f"邮件通知：{'已发送' if self.sender_email else '未配置邮箱，跳过'}"
            )

        # ── 关键词管理 ──────────────────────────────────────
        elif sub in ("kw", "keyword"):
            if len(parts) < 2 or parts[1].lower() == "list":
                yield event.plain_result(self._keywords_text())
                return

            action = parts[1].lower()
            word   = " ".join(parts[2:]) if len(parts) > 2 else ""

            if action == "add":
                if not word:
                    yield event.plain_result("❌ 用法：/guardian kw add <关键词>")
                    return
                custom = self.data.setdefault("custom_keywords", [])
                if word in custom:
                    yield event.plain_result(f"⚠️  关键词「{word}」已存在")
                else:
                    custom.append(word)
                    self._save_data()
                    yield event.plain_result(f"✅ 已添加关键词：「{word}」")

            elif action in ("remove", "del"):
                if not word:
                    yield event.plain_result("❌ 用法：/guardian kw remove <关键词>")
                    return
                custom = self.data.get("custom_keywords", [])
                if word in custom:
                    custom.remove(word)
                    self._save_data()
                    yield event.plain_result(f"✅ 已删除关键词：「{word}」")
                else:
                    yield event.plain_result(f"❌ 自定义关键词「{word}」不存在（内置关键词不可删除）")

            elif action == "clear":
                self.data["custom_keywords"] = []
                self._save_data()
                yield event.plain_result("✅ 已清空所有自定义关键词（内置关键词保留）")

            else:
                yield event.plain_result("❌ 未知操作，可用：list / add / remove / clear")

        # ── 检测测试 ────────────────────────────────────────
        elif sub == "test":
            if len(parts) < 2:
                yield event.plain_result("❌ 用法：/guardian test <文本>")
                return
            test_text = " ".join(parts[1:])
            kw = self._detect_insult(test_text)
            if kw:
                yield event.plain_result(f"⚠️  检测命中！匹配关键词：「{kw}」\n该文本会触发拉黑。")
            else:
                yield event.plain_result(f"✅ 未检测到辱骂内容，该文本不会触发拉黑。")

        # ── 状态概览 ────────────────────────────────────────
        elif sub == "status":
            yield event.plain_result(self._status_text())

        # ── 帮助 ────────────────────────────────────────────
        elif sub in ("help", "?"):
            yield event.plain_result(self._help_text())

        else:
            yield event.plain_result(f"❓ 未知子命令「{sub}」\n" + self._help_text())

    # ────────────────────────────────────────────────────────────
    # 文本生成工具
    # ────────────────────────────────────────────────────────────

    def _help_text(self) -> str:
        return (
            f"🛡️  Guardian 守护插件 v1.1.0\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📋 黑名单管理\n"
            f"  /guardian list            查看黑名单（控制台同步刷新）\n"
            f"  /guardian block <QQ> [原因]  手动拉黑用户\n"
            f"  /guardian unblock <QQ>    解除用户黑名单\n"
            f"\n"
            f"🔑 关键词管理\n"
            f"  /guardian kw list         查看全部关键词\n"
            f"  /guardian kw add <词>     添加自定义关键词\n"
            f"  /guardian kw remove <词>  删除自定义关键词\n"
            f"  /guardian kw clear        清空自定义关键词\n"
            f"\n"
            f"🔧 其他\n"
            f"  /guardian status          查看插件运行状态\n"
            f"  /guardian test <文本>     测试辱骂检测\n"
            f"  /guardian help            显示本帮助\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"保护：{self.bot_name} | 黑名单：{len(self.data['blacklist'])} 人"
        )

    def _blacklist_text(self) -> str:
        bl = self.data["blacklist"]
        if not bl:
            return "✅ 黑名单为空，暂无被拉黑用户。"
        lines = [f"🚫 黑名单列表（共 {len(bl)} 人）", "━━━━━━━━━━━━━━━━━━━━━━"]
        for i, (uid, info) in enumerate(bl.items(), 1):
            lines.append(
                f"{i}. QQ: {uid}\n"
                f"   时间：{info.get('time','未知')}\n"
                f"   群组：{info.get('group_id','未知') or '未知'}\n"
                f"   原因：{info.get('reason','未知')[:50]}"
            )
            if i < len(bl):
                lines.append("   ─────────────────────")
        lines.append(f"\n解除命令：/guardian unblock <QQ号>")
        return "\n".join(lines)

    def _keywords_text(self) -> str:
        default = self.default_keywords
        custom  = self.data.get("custom_keywords", [])
        return (
            f"🔑 关键词列表（模糊阈值：{self.fuzzy_threshold}）\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 内置关键词（{len(default)} 个，不可删除）：\n"
            f"  {'  '.join(default)}\n\n"
            f"✏️  自定义关键词（{len(custom)} 个）：\n"
            f"  {'  '.join(custom) if custom else '（暂无，可用 /guardian kw add 添加）'}\n"
            f"\n添加：/guardian kw add <词>  删除：/guardian kw remove <词>"
        )

    def _status_text(self) -> str:
        return (
            f"📊 Guardian 运行状态\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🤖 保护对象    ：{self.bot_name}\n"
            f"🚫 黑名单人数  ：{len(self.data['blacklist'])} 人\n"
            f"🔑 内置关键词  ：{len(self.default_keywords)} 个\n"
            f"✏️  自定义关键词：{len(self.data.get('custom_keywords', []))} 个\n"
            f"📍 模糊匹配阈值：{self.fuzzy_threshold}\n"
            f"🔇 自动禁言    ：{'开启 (' + str(self.mute_duration) + 's)' if self.auto_mute else '关闭'}\n"
            f"👢 自动踢出    ：{'开启' if self.auto_kick else '关闭'}\n"
            f"📧 邮件通知    ：{'已配置（' + self.sender_email + '）' if self.sender_email else '未配置'}\n"
            f"📬 管理员邮箱  ：{self.admin_email}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━"
        )
