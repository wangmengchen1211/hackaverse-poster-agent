-- poster-agent: posters 表 + Storage bucket
-- 与前端共享同一 Supabase 项目；前端用 anon key 只读成功记录，后端用 service_role 写。
-- 依据：.qoder/specs/poster-agent-spec.md §7（Supabase RLS 风险）

-- ── 表 ──
create table if not exists public.posters (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz default now(),

  -- 输入
  user_ref text,                    -- 可选：前端用户软标识
  project_name text,
  team_name text,
  style text not null,              -- daily / cyber / entertainment / character3d / comic / magic
  layout_used text,                 -- A / B / C / generate

  -- 生成的文案（DeepSeek 产出）
  poster_copy jsonb not null,       -- {headline, subheadline, columns:[{title,body}], tags, easter_egg, editor_comment, share_line, ...}

  -- 生成的图
  image_url text not null,          -- Supabase Storage 公共 URL
  image_storage_path text,          -- Storage 内相对路径

  -- 生成元数据
  generation_meta jsonb,            -- {image_model, attempts, validation:{passed,issues}, latency_ms, text_latency_ms}

  -- 状态
  status text not null default 'success'  -- success / failed
);

-- 索引：按用户/时间倒序查询历史列表
create index if not exists posters_user_ref_created_idx
  on public.posters (user_ref, created_at desc);
create index if not exists posters_style_idx
  on public.posters (style);

-- ── RLS ──
alter table public.posters enable row level security;

-- 前端（anon key）只能读成功的记录
drop policy if exists "public read successful posters" on public.posters;
create policy "public read successful posters" on public.posters
  for select
  using (status = 'success');

-- 写操作由后端 service_role 完成（service_role 绕过 RLS，无需额外 policy）
-- 如需允许前端 anon 写（例如收藏），再单独加 policy

-- ── Storage bucket ──
insert into storage.buckets (id, name, public)
  values ('posters', 'posters', true)
  on conflict (id) do nothing;

-- Storage 公共读策略（bucket 设为 public 后已允许匿名读，此处补一条显式策略）
drop policy if exists "public read posters bucket" on storage.objects;
create policy "public read posters bucket" on storage.objects
  for select
  using (bucket_id = 'posters');
