# 签到请假积分管理系统

基于二维码的签到、请假审批和积分计算系统，使用 Flask + SQLite 开发，支持 Docker Compose 一键部署。

**作者**: xiaoheiCat
**GitHub**: https://github.com/xiaoheiCat/pytakeoff
**开源协议**: MIT License

## 功能特性

### 用户功能
- **用户登录**：使用学工号和密码登录系统
- **密码管理**：首次登录强制修改密码，支持自主修改密码
- **签到功能**：扫描二维码快速签到，自动记录签到时间
- **请假申请**：在线提交请假申请，支持上传多个证明附件
- **积分查询**：实时查看个人积分和积分变动记录

### 管理员功能
- **用户管理**：批量导入用户（CSV），批量删除用户，重置用户密码
- **签到管理**：发起签到活动，生成活动码，结束签到自动计算缺勤
- **签到大屏**：实时显示动态刷新的二维码（默认15秒），显示已签到和未签到人员名单
- **请假审批**：审批请假申请，查看请假附件，批准或拒绝请假
- **积分管理**：手动加分扣分，撤销积分记录，导出积分统计表
- **系统设置**：自定义系统标题，设置二维码刷新间隔和各类分值

## 技术栈

- **后端**：Python 3.11, Flask 3.0, Flask-Login
- **数据库**：SQLite 3
- **前端**：HTML5, CSS3, JavaScript (原生)
- **部署**：Docker, Docker Compose, Gunicorn
- **安全**：Werkzeug 密码哈希，CSRF 保护，SQL 注入防护

## 快速开始

### 使用 Docker Compose（推荐）

1. **克隆或下载项目到本地**

2. **配置环境变量**（可选）
```bash
cp .env.example .env
# 编辑 .env 文件修改配置
```

3. **启动服务**
```bash
docker-compose up -d
```

4. **访问系统**
- 用户端：http://localhost:5000
- 管理后台：http://localhost:5000/admin
- 签到大屏：http://localhost:5000/qr

5. **默认管理员账号**
- 用户名：`admin`（可通过环境变量 `ADMIN_USERNAME` 修改）
- 密码：`admin123`（可通过环境变量 `ADMIN_PASSWORD` 修改）
- **首次登录后请立即修改密码！**

### 本地开发

1. **安装依赖**
```bash
pip install -r requirements.txt
```

2. **配置环境变量**
```bash
cp .env.example .env
```

3. **运行应用**
```bash
python app.py
```

4. **访问系统**
- http://localhost:5000

## 使用指南

### 管理员操作流程

#### 1. 用户管理
1. 登录管理后台 → 用户管理
2. 下载 CSV 模板，填写用户信息（学工号、姓名）
3. 上传 CSV 文件批量导入用户
4. 用户默认密码为学工号，首次登录必须修改

#### 2. 发起签到
1. 管理后台 → 签到管理 → 发起签到
2. 设置开始和结束时间（可选，默认立即开始，10分钟后结束）
3. 系统生成 6 位活动码
4. 打开 `/qr` 页面，输入活动码，显示签到大屏
5. 用户扫描二维码完成签到

#### 3. 签到大屏
- 左侧：动态刷新的二维码（默认15秒），下方显示倒计时
- 右侧：已签到/未签到人员列表，可切换查看
- 自动排除已批准请假的人员

#### 4. 请假审批
- 方式一：结束签到前系统自动提示待审批请假
- 方式二：管理后台 → 请假管理 → 查看所有请假记录
- 可查看请假附件，批准或拒绝请假
- 批准后自动按类型扣除相应积分

#### 5. 积分管理
- 自动计算：签到、请假、缺勤自动记录积分
- 手动操作：管理员可手动加分扣分，填写理由
- 撤销记录：可撤销错误的积分记录
- 导出统计：导出包含所有分类的完整积分表

### 用户操作流程

#### 1. 首次登录
1. 使用学工号和密码（默认为学工号）登录
2. 系统强制要求修改密码
3. 修改成功后进入用户首页

#### 2. 扫码签到
1. 扫描签到大屏上的二维码
2. 如未登录，先登录再重新扫描
3. 登录后扫描二维码即可完成签到
4. 页面显示签到成功提示

#### 3. 请假申请
1. 用户首页 → 请假申请
2. 选择请假类型（公假/事假/病假）
3. 填写请假原因
4. 上传证明附件（可选）
5. 提交后等待管理员审批

#### 4. 查看积分
- 用户首页显示当前总积分
- 下方显示所有积分变动记录
- 包括签到、请假、手动加减分等

## 数据模型

### 用户表 (users)
- 学工号、姓名、密码哈希
- 管理员标志、必须修改密码标志

### 签到会话表 (attendance_sessions)
- 活动码、开始时间、结束时间
- 活动状态、创建者

### 签到记录表 (attendance_records)
- 会话ID、用户ID、签到时间
- 签到状态（出勤/缺勤/请假）

### 请假申请表 (leave_requests)
- 用户ID、会话ID（可选）
- 请假类型、原因、状态
- 审批人、审批时间

### 请假附件表 (leave_attachments)
- 请假ID、文件名、文件路径

### 积分记录表 (points_records)
- 用户ID、分数、原因
- 记录类型、关联ID、创建者
- 删除标志（软删除）

### 二维码表 (qr_codes)
- 会话ID、二维码令牌
- 创建时间、过期时间、使用状态

### 系统设置表 (system_settings)
- 键值对存储
- 系统标题、刷新间隔、分值设定

## 安全特性

1. **密码安全**
   - 使用 Werkzeug PBKDF2 SHA256 哈希存储密码
   - 首次登录强制修改密码
   - 密码最小长度 6 位

2. **会话安全**
   - Flask-Login 会话管理
   - 默认会话有效期 365 天（可配置）
   - 支持手动退出登录

3. **二维码安全**
   - 每次生成唯一令牌（32字节 URL 安全字符）
   - 二维码有刷新间隔+5秒的有效期
   - 一次性使用，扫描后立即失效
   - 签到会话结束后所有二维码失效

4. **SQL 注入防护**
   - 所有数据库查询使用参数化语句
   - 不直接拼接用户输入到 SQL

5. **文件上传安全**
   - 使用 secure_filename 过滤文件名
   - 时间戳前缀防止文件名冲突
   - 文件大小限制 16MB

6. **权限控制**
   - 管理员功能使用 @admin_required 装饰器
   - 密码修改检查使用 @password_change_required 装饰器
   - 所有敏感操作需要登录验证

## 环境变量配置

在 `.env` 文件中配置以下变量：

```env
# Flask 密钥（务必修改为随机字符串）
FLASK_SECRET_KEY=your-secret-key-here

# 默认管理员账号
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin123

# 系统标题
SYSTEM_TITLE=签到系统

# 二维码刷新间隔（秒）
QR_REFRESH_INTERVAL=15
```

## 目录结构

```
takeoff_system/
├── app.py                      # 主应用入口
├── app_attendance.py           # 签到相关路由
├── app_leave_points.py         # 请假和积分路由
├── models.py                   # 用户模型
├── database.py                 # 数据库初始化
├── requirements.txt            # Python 依赖
├── Dockerfile                  # Docker 镜像配置
├── docker-compose.yml          # Docker Compose 配置
├── .env.example                # 环境变量示例
├── templates/                  # HTML 模板
│   ├── base.html              # 基础模板
│   ├── login.html             # 登录页面
│   ├── index.html             # 用户首页
│   ├── qr_screen.html         # 签到大屏
│   └── admin/                 # 管理后台模板
│       ├── dashboard.html     # 后台首页
│       ├── users.html         # 用户管理
│       ├── attendance.html    # 签到管理
│       ├── leave.html         # 请假管理
│       ├── points.html        # 积分管理
│       └── settings.html      # 系统设置
├── data/                       # 数据目录（自动创建）
│   └── database.db            # SQLite 数据库
└── uploads/                    # 上传文件目录（自动创建）
```

## 常见问题

### 1. 如何修改管理员密码？
登录管理后台后，点击"修改密码"即可修改。

### 2. 如何重置用户密码？
管理后台 → 用户管理 → 找到对应用户 → 点击"重置密码"，密码将重置为学工号。

### 3. 二维码刷新太快或太慢？
管理后台 → 系统设置 → 修改"二维码刷新间隔"。

### 4. 如何修改积分规则？
管理后台 → 系统设置 → 修改各类请假和缺勤的分值。

### 5. 数据如何备份？
备份 `data/database.db` 文件和 `uploads/` 目录即可。

### 6. 如何更新系统？
```bash
docker-compose down
docker-compose pull
docker-compose up -d
```

## 技术支持

如遇问题，请检查：
1. Docker 和 Docker Compose 是否正确安装
2. 端口 5000 是否被占用
3. 数据目录是否有写入权限
4. 浏览器控制台是否有错误信息

## 贡献指南

欢迎提交 Issue 和 Pull Request！

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

## 开源协议

MIT License - 详见 LICENSE 文件

本项目供学习和内部使用，如用于商业用途请遵守相关法律法规。

## 致谢

- Flask Web 框架
- SQLite 数据库
- QRCode 库
- 所有贡献者

## 联系方式

- GitHub: https://github.com/xiaoheiCat/pytakeoff
- Issues: https://github.com/xiaoheiCat/pytakeoff/issues

## 更新日志

### v1.0.0 (2024)
- 初始版本发布
- 完整的签到、请假、积分功能
- Docker Compose 一键部署
- 完善的安全防护机制
- 完整的中文文档
