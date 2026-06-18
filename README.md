# Poster Director Agent

产品发布报纸生成后端服务。输入项目 PRD + 0-3 张照片 + 6 种风格之一，自动生成一张中文报纸头版图片，文案与图片持久化到 Supabase（DB + Storage），供前端共享读取。

## 架构

```
前端 → POST /api/generate-poster → poster-agent(Python FastAPI)
                                       ├─ Step1 解析(DeepSeek) → project_brief
                                       ├─ Step2 文案(DeepSeek) → poster_copy（每栏目≤200字）
                                       ├─ Step3 组装(skill×2)  → final_prompt + 参考图
                                       ├─ Step4 生图(gpt-image-2) → image
                                       ├─ Step5 校验(规则)
                                       └─ Step6 持久化(Supabase DB+Storage)
```

## 6 种风格

| key | 名称 | 默认排版 | 参考图 |
|-----|------|---------|--------|
| daily | 经典日报风 | A | references/daily.jpg |
| cyber | 未来赛博风 | B | references/cyber.jpeg |
| entertainment | 娱乐头条风 | 娱乐专属 | references/entertainment.jpg |
| character3d | 3D人物风 | A | references/character3d.jpeg |
| comic | 漫画分镜风 | B | references/comic.jpeg |
| magic | 魔法学院日报风 | C | references/magic.jpeg |

## 本地启动

```powershell
cd "poster agent/poster-agent"

# 1. 安装依赖
python -m pip install -r requirements.txt

# 2. 配置环境变量（复制 .env.example 为 .env，填入 KEY 值）
#    严禁提交 .env（.gitignore 已排除）

# 3. 启动服务
python -m uvicorn app.main:app --reload --port 8766
```

健康检查：`GET http://127.0.0.1:8766/api/health`

## Task 0：API 连通性验证（首次使用必做）

```powershell
# DeepSeek
python scripts/check_deepseek.py
# 预期：打印 HTTP 200 + 耗时 + JSON 模式可用

# gpt-image-2 (llmgateway 中转)
python scripts/check_image_api.py
# 预期：自动探测端点 + 响应格式 + 耗时（>60s 需部署改异步）
```

脚本会读取项目根 `.env`。若 dotenv 未装：`pip install python-dotenv`。

## 环境变量（.env）

| KEY | 用途 | 必需 |
|-----|------|------|
| DEEPSEEK_API_KEY | DeepSeek 文本生成 | 是 |
| DEEPSEEK_BASE_URL | 默认 https://api.deepseek.com | 否 |
| DEEPSEEK_MODEL | 默认 deepseek-chat | 否 |
| IMAGE_API_KEY | llmgateway 中转密钥 | 是 |
| IMAGE_BASE_URL | 默认 https://www.llmgateway.cn | 否 |
| IMAGE_MODEL | 默认 gpt-image-2 | 否 |
| IMAGE_PATH | 默认 /v1/images/generations（Task 0 实测后调整） | 否 |
| SUPABASE_URL | Supabase 项目 URL | 是(Task4+) |
| SUPABASE_SERVICE_KEY | service_role key（后端写） | 是(Task4+) |
| SUPABASE_ANON_KEY | anon key（前端读，后端可选） | 否 |
| PORT | 默认 8766 | 否 |
| CORS_ORIGINS | 允许的前端来源（逗号分隔） | 否 |

## Supabase 配置（与前端共享）

1. 在 Supabase 项目 SQL Editor 执行 `supabase/migrations/0001_posters_table.sql`
2. 建表 + RLS 策略：前端 anon key 只能读 `status='success'` 记录，后端 service_role 写
3. Storage bucket `posters` 设为 public，海报图返回公共 URL

## API 接口

### POST /api/generate-poster （multipart/form-data）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| prd | text | 是 | 项目 PRD / 描述 |
| style | text | 是 | 6 风格 key 之一 |
| project_name | text | 否 | 项目名 |
| team_name | text | 否 | 团队名 |
| event_name | text | 否 | 活动名 |
| layout_mode | text | 否 | random(默认) / generate |
| user_ref | text | 否 | 前端用户标识 |
| options | text(json) | 否 | 如 `{"event_name":"Hackathon"}` |
| images | file[] | 否 | 0-3 张照片 |

响应：
```json
{
  "status": "success",
  "poster_id": "uuid",
  "image_url": "https://xxx.supabase.co/storage/v1/object/public/posters/xxx.png",
  "poster_copy": {"headline": "...", "columns": [...]},
  "style": "daily",
  "layout_used": "A",
  "generation_meta": {"image_model": "gpt-image-2", "attempts": 1, "latency_ms": 35000}
}
```

curl 示例：
```bash
curl -X POST http://127.0.0.1:8766/api/generate-poster \
  -F "prd=我的项目是一个 AI 工作流助手..." \
  -F "style=daily" \
  -F "project_name=PromptPilot" \
  -F "images=@/path/to/photo.jpg"
```

### GET /api/styles
返回 6 风格元数据（供前端选择器）。

### GET /api/posters?user_ref=xxx&limit=20
历史海报列表（前端也可直接用 supabase-js 查 `posters` 表）。

### GET /api/posters/{id}
单张海报详情。

## 前端对接要点

- 生成海报：前端 POST `/api/generate-poster`（multipart，传 prd/style/images）
- 展示历史：前端可用 supabase-js 直接 `from('posters').select('*').eq('status','success')`，anon key 即可读
- 图片引用：`image_url` 是 Supabase Storage 公共 URL，可直接 `<img src={image_url} />`

## 部署（Vercel）

1. 推送代码到 Git
2. Vercel 导入项目，选 `poster agent/poster-agent` 为 Root Directory
3. 在 Vercel 项目设置里配齐环境变量（同 `.env` 的 KEY 名）
4. 执行过 Supabase migration
5. 部署后前端调 `https://<your-vercel>.vercel.app/api/generate-poster`

**超时风险**：Vercel 函数 60s 上限。若 Task 0 实测生图 >60s，需把主接口改异步（POST 返 job_id，`GET /api/jobs/{id}` 轮询）。

## 治理

- 项目 Spec：`.qoder/specs/poster-agent-spec.md`
- 宪法 §7：AI 严禁读写 `.env`，仅登记 KEY 名
- 进度单一事实源：Qoder 原生 Plan 视图 + spec.md 状态字段
