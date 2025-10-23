# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 提供在此代码仓库中工作的指导。

## 项目概述

QR码签到请假积分管理系统 - 基于 Flask 的签到、请假管理和积分计算系统，使用二维码进行签到。采用 SQLite 数据库，专为教育机构设计，用于追踪学生考勤和请假申请。

**作者**: xiaoheiCat
**GitHub**: https://github.com/xiaoheiCat/pytakeoff

## 开发环境设置

### 快速开始
```bash
# 本地开发
pip install -r requirements.txt
cp .env.example .env
python app.py

# Docker 部署（推荐）
docker-compose up -d
```

### 运行应用
- 开发模式: `python app.py` (运行在 http://localhost:5000)
- 生产模式: 通过 Docker Compose 使用 Gunicorn
- 默认管理员账号: `admin` / `admin123` (首次登录必须修改)

## 架构概览

### 模块化路由注册模式
应用采用**插件式架构**，路由通过函数调用注册而非使用蓝图：

- **`app.py`**: 核心应用初始化、认证装饰器和基础用户路由
- **`app_attendance.py`**: 包含 `register_attendance_routes(app, ...)` - 所有二维码和签到功能
- **`app_leave_points.py`**: 包含 `register_leave_points_routes(app, ...)` - 请假审批和积分管理

路由模块在 **app.py 底部导入**（装饰器定义之后），通过调用注册函数并传入应用实例和所需装饰器来完成注册。

### 数据库架构 (SQLite)
系统使用 **8 个相互关联的表**，具有精心设计的外键关系：

1. **users** - 学生/管理员账户，含密码哈希
2. **system_settings** - 键值对配置存储（标题、间隔、分值）
3. **attendance_sessions** - 签到活动，包含 6 位活动码
4. **attendance_records** - 个人签到记录（session+user 唯一约束）
5. **leave_requests** - 请假申请，含审批工作流
6. **leave_attachments** - 文件上传，关联请假申请（级联删除）
7. **points_records** - 所有积分事务，软删除（is_deleted 标志）
8. **qr_codes** - 一次性使用的二维码令牌，含过期时间戳

**关键约束**：
- `attendance_records`: UNIQUE(session_id, user_id) 防止重复签到
- `qr_codes`: 通过 `is_used` 标志一次性使用，通过 `expires_at` 限时
- `points_records`: 软删除保留审计轨迹

### 二维码安全流程
1. 管理员创建会话 → 生成 6 位 `activity_code`
2. 管理员打开 `/qr` → 输入活动码 → 显示二维码大屏
3. 前端每 N 秒调用 `/api/qr/generate/<session_id>`
4. 后端生成唯一 32 字节 `qr_token`，`expires_at` = 当前时间 + 间隔 + 5秒
5. 二维码编码 URL: `/checkin/<qr_token>`
6. 用户扫描 → 如未登录，登录后重定向回来
7. 后端验证：令牌未使用、未过期、会话活跃
8. 标记令牌已使用，创建签到记录
9. 一个令牌 = 一次签到（防止令牌重用）

### 积分计算系统
积分在签到事件中**自动计算**，使用**可配置的值**：

- **创建签到记录** → 无积分（出勤为默认）
- **请假批准** → 应用请假类型积分（公假: 0，事假: -1，病假: -0.5）
- **会话结束** → 缺勤用户获得 `absent_points` (默认 -2)
- **手动调整** → 管理员可加分/扣分并填写理由

**record_type 值**: `'absence'`、`'leave'`、`'manual'`、`'manual_leave'`

所有积分记录追踪 `created_by` 用于审计，使用 `is_deleted` 进行软删除（撤销）。

### 认证与授权流程
- **Flask-Login** 管理会话（默认 365 天过期）
- **两个自定义装饰器**：
  - `@admin_required`: 检查 `current_user.is_admin`
  - `@password_change_required`: 通过 `must_change_password` 标志强制首次登录修改密码
- **密码安全**: Werkzeug PBKDF2-SHA256，最少 6 位
- **二维码登录流程**: 未认证扫描将 `pending_checkin` 存入会话，登录后重定向

### 数据库连接模式
每个路由遵循此模式以保证线程安全：
```python
conn = get_db()  # 创建新连接
cursor = conn.cursor()
# ... 执行查询 ...
conn.commit()  # 写操作需要
conn.close()   # 始终关闭
```
**切勿跨请求重用连接** - 尽管使用了 SQLite `check_same_thread=False`，但每个请求都获取新连接。

## 关键实现细节

### 活动码生成
6 位字符来自 `[a-zA-Z0-9]`，通过 `secrets.choice()` 进行碰撞检查 - **不是 UUID**，为了用户友好。

### CSV 导入/导出
- **导入**: UTF-8-BOM 编码 (`utf-8-sig`) 以兼容 Excel
- **导出**: 相同编码，包含所有积分类别的详细分解
- 模板提供示例行用于用户指导

### 文件上传安全
- `secure_filename()` 清理文件名
- 时间戳前缀防止冲突: `{YYYYMMDDHHmmss}_{filename}`
- 16MB 最大上传限制
- 存储在 `uploads/` 目录（启动时创建）

### 设置管理
所有可配置值通过 `get_setting()` / `set_setting()` 存储在 `system_settings` 表：
- `system_title`: 显示名称
- `qr_refresh_interval`: 二维码刷新间隔秒数（默认 15）
- `*_leave_points`: 各请假类型的积分值
- `absent_points`: 缺勤惩罚

设置在**每个请求中缓存**（非应用级） - 总是查询最新值。

### 模板上下文
所有模板接收 `system_title` - 在每个路由中通过 `get_setting()` 检索。模板使用 Jinja2，**自动转义已启用**（无原始 HTML 注入）。

## 常见修改模式

### 添加新路由
1. 选择合适的模块（基础用 `app.py`，或 `app_attendance.py`、`app_leave_points.py`）
2. 如果在路由模块中，添加到注册函数内
3. 应用装饰器: `@login_required`、`@admin_required`、`@password_change_required`
4. 获取数据库连接，执行操作，关闭连接
5. Flash 消息用于用户反馈: `flash('消息', 'success|error|warning')`

### 添加数据库表
1. 在 `database.py` 的 `init_db()` 中添加 CREATE TABLE
2. 使用 `IF NOT EXISTS` 使其幂等
3. 考虑外键和 CASCADE 行为
4. 如果表与用户相关，在 `models.py` 中添加辅助方法

### 更改积分值
不要硬编码 - 始终使用设置：
```python
points = float(get_setting('point_type_key', 'default_value'))
```

### 添加系统设置
1. 添加到 `database.py` 的 `init_db()` 中的 `default_settings` 字典
2. 在 `templates/admin/settings.html` 中添加表单字段
3. 更新 `admin_settings()` 路由以处理新字段

## 安全考虑

### SQL 注入防护
**始终使用参数化查询** - 切勿字符串插值：
```python
# 正确
cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))

# 错误 - 不要这样做
cursor.execute(f'SELECT * FROM users WHERE id = {user_id}')
```

### 二维码安全属性
- **唯一令牌**: `secrets.token_urlsafe(32)` = 加密随机
- **限时**: 每次扫描检查 `expires_at`
- **一次性使用**: `is_used` 标志防止重放
- **会话绑定**: 会话结束后无效

### 密码存储
- **切勿存储明文** - 始终使用 `generate_password_hash()` 哈希
- **验证使用**: `check_password_hash(stored_hash, input_password)`
- 默认密码 = `student_id`，`must_change_password=1`

### 文件上传验证
当前实现使用 `secure_filename()`，但考虑添加：
- MIME 类型检查
- 文件扩展名白名单
- 生产环境病毒扫描

## 测试与调试

### 数据库检查
```bash
sqlite3 data/database.db
.tables
.schema table_name
SELECT * FROM system_settings;
```

### 重置管理员密码
```python
python -c "
from database import get_db
from werkzeug.security import generate_password_hash
conn = get_db()
cursor = conn.cursor()
cursor.execute('UPDATE users SET password_hash = ?, must_change_password = 1 WHERE is_admin = 1',
               (generate_password_hash('newpassword'),))
conn.commit()
"
```

### 查看日志
```bash
docker-compose logs -f
docker-compose logs web --tail=100
```

## 项目特定约定

### Flash 消息类别
- `'success'`: 绿色，操作完成
- `'error'`: 红色，操作失败
- `'warning'`: 黄色，警告或需要注意

### URL 模式
- 用户路由: `/`、`/login`、`/leave/request`、`/checkin/<token>`
- 管理路由: `/admin/*`（都需要管理员角色）
- API 路由: `/api/*`（返回 JSON，不渲染页面）
- 二维码显示: `/qr`（全屏信息亭模式）

### 命名约定
- 数据库列: `snake_case`
- Python 函数: `snake_case`
- Flask 路由: URL 中使用 `kebab-case`
- 模板文件: `lowercase.html`
- CSS 类: `kebab-case`

### 中文文本
UI 使用中文（zh-CN）。修改面向用户的文本时：
- 保持术语一致性
- Flash 消息应简洁（< 20 字符）
- 正式场合使用礼貌形式（"您"而非"你"）

## 部署注意事项

### 环境变量
`.env` 中的关键变量：
- `FLASK_SECRET_KEY`: 生产环境**必须随机**（使用 `secrets.token_hex(32)`）
- `ADMIN_USERNAME` / `ADMIN_PASSWORD`: 初始管理员凭据
- `SYSTEM_TITLE`: 显示名称
- `QR_REFRESH_INTERVAL`: 二维码刷新秒数

### 数据持久化
Docker 卷挂载：
- `./data` → `/app/data`（SQLite 数据库）
- `./uploads` → `/app/uploads`（请假附件）

**备份这些目录**以进行灾难恢复。

### 生产检查清单
1. 将 `FLASK_SECRET_KEY` 改为随机值
2. 从默认值更改 `ADMIN_PASSWORD`
3. 设置 `debug=False`（已配置）
4. 配置 HTTPS 反向代理（推荐 Nginx）
5. 设置定期数据库备份
6. 监控上传文件的磁盘空间

## 常见陷阱

### 不要忘记关闭连接
始终 `conn.close()`，即使在错误路径中 - 考虑使用 try/finally 或上下文管理器。

### 二维码令牌过期计算
令牌在 `refresh_interval + 5` 秒后过期 - +5 秒宽限期防止刷新和扫描之间的竞态条件。

### 请假审批工作流
结束签到会话时，系统**强制审批待处理的请假**才允许关闭会话。这防止了孤立的请假申请。

### 积分软删除
切勿 `DELETE FROM points_records` - 始终 `UPDATE points_records SET is_deleted = 1` 以保留审计轨迹。查询必须过滤 `is_deleted = 0`。

### 会话 vs Flask 会话
- `attendance_sessions` = 签到事件的数据库表
- `flask_session` = 用户登录会话存储
- 不要混淆变量名！
