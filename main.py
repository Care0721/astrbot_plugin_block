import json
import os
from astrbot.api.plugin import AstrBotPlugin, PluginContext, star
from astrbot.api.message import MessageEvent, GroupMessageEvent
from astrbot.api.web import Response, Request

DATA_FILE = os.path.join(os.path.dirname(__file__), "data.json")
DEFAULT_KEYWORDS = ["傻逼", "弱智", "垃圾", "废物", "脑残", "sb", "nmsl"]
UNBLOCK_EMAIL = "carenb666@foxmail.com"

class MonikaBlockPlugin(AstrBotPlugin):
    def __init__(self, context: PluginContext):
        super().__init__(context)
        self.data = self.load_data()
        if "blocked_users" not in self.data:
            self.data["blocked_users"] = {}   # {group_id: [user_id]}
        if "keywords" not in self.data:
            self.data["keywords"] = DEFAULT_KEYWORDS
        self.save_data()

    def load_data(self):
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def save_data(self):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    @star.on_message()
    async def on_message(self, event: MessageEvent):
        if not isinstance(event, GroupMessageEvent):
            return
        # 忽略机器人自己的消息
        if event.get_self_id() == event.get_user_id():
            return

        group_id = str(event.get_group_id())
        user_id = str(event.get_user_id())

        # 1. 已屏蔽用户 → 直接拦截并回复提醒
        if group_id in self.data["blocked_users"] and user_id in self.data["blocked_users"][group_id]:
            await event.send_message(
                f"检测到您处于黑名单中，所有功能已禁用。如需解除，请联系管理员：{UNBLOCK_EMAIL}"
            )
            return True   # 返回 True 阻止事件继续传播，其他插件不再处理

        # 2. 正常用户 → 检测辱骂关键词
        raw_text = event.get_message_plain()
        if self.check_insult(raw_text):
            await self.block_user(group_id, user_id)

    def check_insult(self, text: str) -> bool:
        lower_text = text.lower()
        for kw in self.data["keywords"]:
            if kw.lower() in lower_text:
                return True
        return False

    async def block_user(self, group_id: str, user_id: str):
        """仅加入内部黑名单，不踢出群聊"""
        if group_id not in self.data["blocked_users"]:
            self.data["blocked_users"][group_id] = []
        if user_id not in self.data["blocked_users"][group_id]:
            self.data["blocked_users"][group_id].append(user_id)
            self.save_data()

    async def unblock_user(self, group_id: str, user_id: str):
        """从黑名单移除"""
        if group_id in self.data["blocked_users"] and user_id in self.data["blocked_users"][group_id]:
            self.data["blocked_users"][group_id].remove(user_id)
            if not self.data["blocked_users"][group_id]:
                del self.data["blocked_users"][group_id]
            self.save_data()

    # ───────── WebUI 路由 ─────────
    def register_routes(self):
        @self.context.webui.route("/monika-block", methods=["GET"])
        async def index(request: Request):
            return self.serve_index()

        @self.context.webui.route("/api/plugin/monika-block/list", methods=["GET"])
        async def get_blocked_users(request: Request):
            return Response.json(self.data["blocked_users"])

        @self.context.webui.route("/api/plugin/monika-block/add", methods=["POST"])
        async def add_block(request: Request):
            data = await request.json()
            group_id = data.get("group_id")
            user_id = data.get("user_id")
            if not group_id or not user_id:
                return Response.json({"ok": False, "msg": "群号或QQ号不能为空"}, status=400)
            await self.block_user(str(group_id), str(user_id))
            return Response.json({"ok": True, "msg": f"已将 {user_id} 加入黑名单（群 {group_id}）"})

        @self.context.webui.route("/api/plugin/monika-block/remove", methods=["POST"])
        async def remove_block(request: Request):
            data = await request.json()
            group_id = data.get("group_id")
            user_id = data.get("user_id")
            if not group_id or not user_id:
                return Response.json({"ok": False, "msg": "参数缺失"}, status=400)
            await self.unblock_user(str(group_id), str(user_id))
            return Response.json({"ok": True, "msg": f"已将 {user_id} 从黑名单移除"})

        @self.context.webui.route("/api/plugin/monika-block/keywords", methods=["GET"])
        async def get_keywords(request: Request):
            return Response.json({"keywords": self.data["keywords"]})

        @self.context.webui.route("/api/plugin/monika-block/keywords", methods=["POST"])
        async def set_keywords(request: Request):
            data = await request.json()
            new_keywords = data.get("keywords")
            if not isinstance(new_keywords, list):
                return Response.json({"ok": False, "msg": "关键词需为数组"}, status=400)
            self.data["keywords"] = new_keywords
            self.save_data()
            return Response.json({"ok": True, "msg": "关键词已更新"})

    def serve_index(self):
        html = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Monika 辱骂屏蔽管理</title>
            <style>
                body { font-family: sans-serif; margin: 20px; }
                table { border-collapse: collapse; width: 100%; max-width: 800px; }
                th, td { border: 1px solid #ccc; padding: 8px 12px; text-align: left; }
                th { background-color: #f0f0f0; }
                button { cursor: pointer; }
                .section { margin-bottom: 30px; }
                input { padding: 6px; width: 200px; margin-right: 10px; }
                textarea { width: 400px; }
            </style>
        </head>
        <body>
            <h1>Monika 辱骂屏蔽控制台</h1>
            <p style="color:#555;">辱骂者将被加入<strong>内部黑名单</strong>，Bot 会忽略其所有消息并自动回复提示。</p>
            <div class="section">
                <h3>当前黑名单（群号 - QQ号）</h3>
                <table id="blockedTable">
                    <thead><tr><th>群号</th><th>QQ号</th><th>操作</th></tr></thead>
                    <tbody></tbody>
                </table>
            </div>
            <div class="section">
                <h3>手动添加黑名单</h3>
                <input type="text" id="addGroup" placeholder="群号">
                <input type="text" id="addUser" placeholder="QQ号">
                <button onclick="addBlock()">加入黑名单</button>
                <span id="addMsg" style="color:red;"></span>
            </div>
            <div class="section">
                <h3>关键词管理（每行一个）</h3>
                <textarea id="keywordsArea" rows="5"></textarea><br>
                <button onclick="updateKeywords()">更新关键词</button>
                <span id="kwMsg" style="color:red;"></span>
            </div>
            <script>
                async function fetchList() {
                    const res = await fetch('/api/plugin/monika-block/list');
                    const data = await res.json();
                    const tbody = document.querySelector('#blockedTable tbody');
                    tbody.innerHTML = '';
                    for (const [groupId, users] of Object.entries(data)) {
                        for (const userId of users) {
                            const row = tbody.insertRow();
                            row.insertCell().textContent = groupId;
                            row.insertCell().textContent = userId;
                            const btnCell = row.insertCell();
                            const btn = document.createElement('button');
                            btn.textContent = '移除黑名单';
                            btn.onclick = () => removeBlock(groupId, userId);
                            btnCell.appendChild(btn);
                        }
                    }
                }

                async function removeBlock(groupId, userId) {
                    await fetch('/api/plugin/monika-block/remove', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({group_id: groupId, user_id: userId})
                    });
                    fetchList();
                }

                async function addBlock() {
                    const groupId = document.getElementById('addGroup').value.trim();
                    const userId = document.getElementById('addUser').value.trim();
                    const res = await fetch('/api/plugin/monika-block/add', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({group_id: groupId, user_id: userId})
                    });
                    const data = await res.json();
                    document.getElementById('addMsg').textContent = data.msg;
                    if (data.ok) {
                        document.getElementById('addGroup').value = '';
                        document.getElementById('addUser').value = '';
                        fetchList();
                    }
                }

                async function loadKeywords() {
                    const res = await fetch('/api/plugin/monika-block/keywords');
                    const data = await res.json();
                    document.getElementById('keywordsArea').value = data.keywords.join('\\n');
                }

                async function updateKeywords() {
                    const raw = document.getElementById('keywordsArea').value;
                    const keywords = raw.split('\\n').map(s => s.trim()).filter(s => s.length > 0);
                    const res = await fetch('/api/plugin/monika-block/keywords', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({keywords: keywords})
                    });
                    const data = await res.json();
                    document.getElementById('kwMsg').textContent = data.msg;
                }

                fetchList();
                loadKeywords();
            </script>
        </body>
        </html>
        """
        return Response.html(html)