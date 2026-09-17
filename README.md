# lit-push · 你的专属文献推送系统

每天早上 8 点（北京时间）自动从 **知网期刊 RSS / arXiv / OpenAlex / Crossref 期刊目录 / 期刊 RSS**
检索你关心的关键词与期刊，自动去重，按 **四大研究方向自动归类**，
可选 **AI 深度加工**（中文摘要、核心观点与脉络、可借鉴处、未来研究趋向、可延伸创新点），
然后推送到 **飞书（分类卡片，含“未来方向与创新点”汇编卡）/ 邮件 / 微信 / Telegram**。
完全跑在免费的 GitHub Actions 上，**不需要自己的服务器**。

> 当前 `config.yaml` 已按 **语言智能翻译与传播** 方向预配置：
>
> - **中文核心刊 25 本**（知网官方 RSS，免费合法）：《中国翻译》《上海翻译》《中国科技翻译》
>   《民族翻译》《语言与翻译》5 本翻译专刊全收；《外语界》《外语教学与研究》《中国外语》
>   《外语电化教学》《现代外语》《外国语》等 10 本外语类 CSSCI/北大核心，
>   以及《国际传播》《国际新闻界》《新闻记者》《现代传播》等 10 本传播类核心刊，
>   后两类按翻译/国际传播关键词过滤。
> - **国际期刊 47 本**（Crossref，按 ISSN 锁刊）：Target、Meta、Perspectives、
>   Translation Studies、The Translator、Across、Interpreting、ITT、Babel、JoSTrans 生态、
>   Machine Translation 等 18 本翻译/口译/技术专刊，加 New Media & Society、
>   Journal of Communication、Digital Journalism、Chinese Journal of Communication、
>   Global Media and China 等传播刊，以及 System、ReCALL、CALL 等外语技术刊。
> - **arXiv**（cs.CL、cs.CY）追踪机器翻译、口译技术、大模型翻译的技术前沿；
>   **OpenAlex** 跨刊扫描中英文术语。
> - 文章自动归入四大板块：**一、翻译史；二、翻译与传播；三、翻译教育/翻译教学；
>   四、人工智能与翻译**；都不符合的进“五、翻译学综合与其他”。
> 其他方向照「配置示例」一节改关键词即可。

## 它长什么样

```
数据源（知网期刊 RSS / arXiv / OpenAlex / Crossref / 期刊 RSS）
      ↓  ① 定时采集（GitHub Actions 每天 8:00）
关键词过滤 + 非论文条目剔除（稿约/征稿/启事/栏目导读/会议新闻）
      ↓
跨源去重 + 历史去重（data/seen.json）
      ↓  ② 只留真正新增的研究论文
四大方向自动归类（规则强/弱特征词，中英文双词表；LLM 开启时由 AI 精分）
      ↓  ③ 每篇标出研究方向（sub_topic）
可选 AI 深度加工：关键词 / 中文摘要 / 核心观点与脉络 / 可借鉴处 /
                未来研究趋向 / 可延伸创新点 / 0–10 评分
      ↓
推送：飞书卡片（总览卡 + 四大类卡片 + 绿色“未来方向与创新点汇编”卡，自动分页）
      邮件 HTML 日报 / 微信 PushPlus / Telegram
      ↓  ④ 同时在 data/reports/ 存档 Markdown + HTML 日报
```

## 数据源各管什么

| 源 | 覆盖 | 费用/认证 | 适合 |
| --- | --- | --- | --- |
| **知网期刊 RSS** | 中文期刊最近一期目录（篇名、作者、日期、多数含摘要） | 完全免费、无需登录、无需爬虫 | 国内 CSSCI/北大核心/AMI 刊 |
| **arXiv** | 理工预印本（NLP、机器翻译、计算传播技术侧） | 完全免费 | 语言智能、计算机方向 |
| **OpenAlex** | 2.5 亿+ 篇期刊论文，含人文社科，中英文可检 | 免费无 Key（填邮箱进礼貌池更快） | 按关键词跨刊扫描 |
| **Crossref** | 全球有 DOI 的期刊目录，按 ISSN 锁定单本期刊 | 免费无 Key | “盯死”国际核心刊每期目录 |
| **期刊 RSS** | 任何提供 feed 的期刊/学会网站（如 JoSTrans 官网） | 免费 | 没有 DOI 体系的开放获取刊 |

## 文件结构

```
lit-push/
├── main.py                  # 程序入口
├── config.yaml              # ★ 唯一需要你改的文件（关键词/期刊/渠道开关）
├── requirements.txt         # 依赖（Actions 自动安装）
├── .github/workflows/daily.yml   # 定时任务（已写好，不用改）
├── data/                    # 运行后自动生成：seen.json 去重记录 + reports/ 日报
└── litpush/
    ├── sources.py           # 采集知网 RSS / arXiv / OpenAlex / Crossref / RSS
    ├── classify.py          # 四大类规则归类（强特征词 + 弱信号二轮兜底）
    ├── processing.py        # 过滤、非论文条目剔除、去重、AI 深度加工
    ├── delivery.py          # 飞书卡片/邮件/微信/Telegram 渲染与推送
    └── utils.py             # 工具函数
```

## 部署只需 5 步（网页操作，不用在电脑上装任何东西）

### 第 1 步：建一个 GitHub 仓库

1. 打开 <https://github.com> 注册/登录（邮箱即可，免费）。
2. 右上角 **+ → New repository**，名字填 `lit-push`，选 **Public**，其他默认，点 Create。
3. 进入仓库页面，点 **"uploading an existing file"**（或 Add file → Upload files），
   把本文件夹里的**所有内容**（含 `.github` 文件夹；若看不到隐藏文件夹，
   直接把整个 `lit-push` 文件夹拖进去也可以）拖进去，页面底部 **Commit changes**。

> 注意：`.github` 是隐藏文件夹。Windows 文件资源管理器“查看”里勾上“隐藏的项目”即可看到。

### 第 2 步：选渠道，拿“密钥”（想用哪个配哪个，至少配一个）

#### 渠道 A：飞书群机器人（国内最推荐，2 分钟）

1. 建一个只有自己的飞书群（群成员至少 2 人时可把小号/同事拉进来再移出，或直接用现有群）。
2. 群设置 → **群机器人 → 添加机器人 → 自定义机器人**。
3. 安全设置勾选 **签名校验**（推荐），会得到一个“签名校验密钥”；
   也可以勾“自定义关键词”并填 `文献`（本系统每条消息都含“文献推送”四字）。
4. 复制 **Webhook 地址**（形如 `https://open.feishu.cn/open-apis/bot/v2/hook/xxxx`）。
5. 记下：`FEISHU_WEBHOOK` = Webhook 地址；若用签名校验，`FEISHU_SECRET` = 签名密钥。

推送形态：1 张总览卡 + 每个方向 1 张分类卡（每卡最多 15 篇，超出自动出续卡）+
1 张绿色的 **“未来研究方向与可延伸创新点汇编”** 卡；卡片按飞书 30KB 限制自动分页，不会截断。

#### 渠道 B：邮件（QQ 邮箱举例，适合收“图文日报”）

1. QQ 邮箱网页版 → 设置 → 账号 → 找到 **POP3/IMAP/SMTP 服务**，开启 IMAP/SMTP。
2. 按提示发短信，得到 **16 位授权码**（不是 QQ 密码）。
3. 记下：`SMTP_USERNAME` = 你的完整邮箱；`SMTP_PASSWORD` = 授权码；
   并在 `config.yaml` 里把 `to` 写成收件邮箱。
4. 163/Gmail 同理，host 改 `smtp.163.com` / `smtp.gmail.com`（Gmail 需应用专用密码）。

#### 渠道 C：微信（PushPlus 服务号推送）

1. 打开 <https://www.pushplus.plus> ，微信扫码登录。
2. 一对一推送 → 复制你的 **token**。
3. 记下：`PUSHPLUS_TOKEN` = token。日报会以图文消息出现在微信“PushPlus”服务号里。

#### 渠道 D：Telegram（Actions 在海外运行，可直连）

1. 在 Telegram 搜索 `@BotFather`，发 `/newbot`，按提示起名，得到 **Bot Token**。
2. 先给你的机器人发一句话（如 `hi`），再找 `@userinfobot` 拿到你的 **数字 Chat ID**。
3. 记下：`TELEGRAM_BOT_TOKEN` = token；Chat ID 直接填进 `config.yaml` 的 `chat_id`。

### 第 3 步：把密钥存进 GitHub Secrets

在仓库页：**Settings → Secrets and variables → Actions → New repository secret**，
把第 2 步记下的东西逐个添加（Name 必须与上面的大写名字完全一致，Value 粘贴真值）：

| Secret 名称 | 什么时候需要 |
| --- | --- |
| `FEISHU_WEBHOOK` / `FEISHU_SECRET` | 用飞书时 |
| `CNKI_RSS_BASE` | 部署了知网国内中继云函数时（见“中文期刊”一节） |
| `SMTP_USERNAME` / `SMTP_PASSWORD` | 用邮件时 |
| `PUSHPLUS_TOKEN` | 用微信时 |
| `TELEGRAM_BOT_TOKEN` | 用 Telegram 时 |
| `LLM_API_KEY` | 想用 AI 深度加工时（见第 5 步） |

### 第 4 步：改配置、开渠道、手动试跑

1. 在仓库里点开 `config.yaml`，右上角铅笔图标编辑，把你选的渠道下的
   `enabled: false` 改成 **`true`**，邮件渠道再填好 `to`。
2. 打开仓库的 **Actions** 标签：首次会提示确认，点 **I understand my workflows...**；
   左侧选 **daily-lit-push** → 右侧 **Run workflow**（绿色按钮）手动跑一次。
3. 第一次运行要拉 70 多个源，约需 3–5 分钟；日志出现 `任务完成` 且渠道日志显示
   “发送成功”，就去飞书/邮箱/微信查收；之后每天 **北京时间 08:00** 自动推送。

### 第 5 步（强烈建议）：开 AI 深度加工

规则分类只能做兜底归类、推送原文摘要；**四大方向精分、中文摘要、核心观点脉络、
未来方向与创新点提炼都依赖 LLM**，体验差距很大。在 `config.yaml` 把 `llm.enabled`
改成 `true`，再加一个 Secret `LLM_API_KEY`：

- **豆包方舟**（推荐国内用户）：登录 [火山方舟控制台](https://console.volcengine.com/ark)
  → 完成个人实名认证 → API Key 管理 → 创建 API Key；再到“开通管理”开通
  `doubao-seed-2-1-pro`（配置默认模型 `doubao-seed-2-1-pro-260915`；
  开通时可勾选“安心体验”，只消耗赠送的免费额度、超额自动暂停，不会产生扣费）。
  `base_url` 保持 `https://ark.cn-beijing.volces.com/api/v3`。
  本系统默认 `batch_size: 3`、`timeout: 300`、`disable_thinking: true`
  （关闭推理模型的思维链，批量结构化输出从“必超时”变为每批约 30–45 秒，已实测稳定；
  78 篇首跑约 15 分钟，日常新增几篇时 1–3 分钟）。
- **DeepSeek**：注册 <https://platform.deepseek.com> 生成 key，
  `base_url` 改 `https://api.deepseek.com`，`model` 填 `deepseek-chat`，
  并把 `disable_thinking` 删掉或设为 `false`（DeepSeek 不认该参数）。

每天通常只有几十篇候选、每篇只发摘要，费用一般在几分到几毛钱/天。
不开通也完全能用，只是规则分类、英文原摘要、无评分。
若只想收 AI 推荐的文章，把 `llm.only_recommended` 改成 `true`（7 分以上才推）。

## 想在自己电脑上先试跑（完全可选）

```bash
pip install -r requirements.txt
python main.py --config config.yaml
```

没配密钥时所有渠道默认关闭，结果只会写到 `data/reports/当天日期.md`，
打开即可预览日报效果，不会真的发消息。

> Windows 提示：若命令行输入 `python` 弹出微软商店，说明系统只有“应用商店占位符”，
> 请到 <https://www.python.org> 安装正式版 Python 3.10+，安装时勾选 *Add python.exe to PATH*。
> 不装也没关系，GitHub Actions 云端运行不依赖你的电脑。

## 中文期刊：知网 RSS 已内置（免费、合法）

知网为每本期刊提供**官方 RSS 订阅**，内容是该刊最近上网的 20 篇文章的
篇名、作者、发表日期和大部分摘要——**免费、无需登录、无需购买数据库、无需爬虫**，
本系统已内置 25 本翻译/外语/传播核心刊（2026 年仍在持续更新，已逐刊实测）：

| 板块 | 期刊（RSS 代码） |
| --- | --- |
| 翻译专刊（全收） | 中国翻译 ZGFY、上海翻译 SHKF、中国科技翻译 KJFY、民族翻译 MZFY、语言与翻译 YYFY |
| 外语/翻译教育（关键词过滤） | 外语界 WYJY、外语教学与研究 WJYY、中国外语 ZGWE、外语电化教学 WYDH、现代外语 XDWY、山东外语教学 SDWY、天津外国语大学学报 TJWG、外国语文研究 WGYJ、外国语 WYXY、外语与外语教学 WYWJ |
| 新闻传播（关键词过滤） | 国际传播 GJCB、国际新闻界 GJXW、新闻记者 XWJZ、新闻大学 XWDX、中国记者 ZGJZ、现代传播 XDCB、新闻与写作 XWXZ、青年记者 QNJZ、新闻爱好者 XWAH、传媒观察 CMGC |

说明与自助增刊：

- feed 地址格式：`https://rss.cnki.net/knavi/rss/四位代码`。
  查代码：打开知网期刊导航 <https://navi.cnki.net> 搜刊名 → 期刊主页点
  **RSS 订阅**，复制到的地址里 `/rss/` 后面那 4 位字母就是代码；
  也可在“发表记”（fabiaoji.com）期刊页看到 `pykm=代码`。
- 加刊：在 `config.yaml` 的 `sources.rss.feeds` 照抄一行，翻译专刊可不配
  `keywords_any`（全收），综合刊建议配过滤词；月刊/双月刊把 `lookback_days`
  设 60–90，避免漏期。
- 程序自动剔除稿约、征稿启事、订阅广告、主持人语、栏目“专题”页、会议新闻等非论文条目。
- 少数期刊暂未找到可用 RSS（如《新闻与传播研究》《对外传播》《当代传播》《新闻界》
  《西安外国语大学学报》《东方翻译》（已停更于 2021 年）），可按上面方法拿到代码后
  自行加一行；拿不到的用下一节的免费全文通道或 Google Scholar 快讯补充。
- **GitHub Actions 海外节点无法直连知网 RSS**（`rss.cnki.net` 对境外 CDN 地域封锁，
  实测 25 个 feed 全部失败）。本系统支持“国内云函数中继”：把一个约 40 行的
  免费云函数（代码在 `deploy/tencent-cnki-relay/index.py`，腾讯云 SCF 事件函数，
  Python 3.10、免鉴权公网 URL、白名单只放行 `/knavi/rss/代码`）部署到国内节点，
  再在 GitHub Secrets 配 `CNKI_RSS_BASE` = 云函数 URL（不带末尾斜杠），
  程序会自动把知网请求改走中继，其余源不受影响。腾讯云云函数每月免费额度足够
  每天数十次 RSS 拉取；不想部署时也可在自己电脑上用“任务计划程序”每天跑
  `python main.py`（国内网络可直连，无需中继）。

## 中文全文怎么免费读（合法通道）

RSS 只给目录和摘要。看到想读的文章，全文走这些**免费合法**渠道，不需要买数据库：

1. **国家哲学社会科学文献中心 NCPSSD**（首选，社科院承建的公益平台）：
   <https://ncpssd.cn> ，注册即免费在线阅读/下载 2200 多种中文期刊、1300 多万篇论文，
   翻译/传播类 CSSCI 期刊基本齐全；另有“期刊论文优先发布系统”可看首发稿。
2. **期刊官网/公众号**：如《上海翻译》官网 shjot2021.shu.edu.cn 开放当期目录与摘要，
   多数期刊公众号会推送当期目录和部分全文。
3. **学校图书馆**：在校学生/校友通过校园网或 VPN 登录图书馆的知网/万方，
   一般已由学校购买，个人无需再付费。
4. **Google Scholar 快讯**：<https://scholar.google.com> 搜中文关键词后点
   “创建快讯”，新论文自动发邮件，可覆盖暂无 RSS 的期刊。
5. **开放获取英文刊**：JoSTrans 等 OA 刊官网直接下全文，也可把官网 feed 填进
   `sources.rss.feeds`。

> 关于“是否要购买/爬取知网内容”：购买的是**全文阅读和数据库使用权**，
> 不是“抓取授权”；知网、万方的服务协议均禁止未经授权的批量爬取全文。
> 本系统只用官方公开的 RSS 目录数据，全文请走上述合法通道，既合规又稳定。

## 四大类归类与关键词怎么调

- 分类规则在 `config.yaml` 的 `classification.categories`：每类有 `keywords`
  （强特征词，标题命中权重 2、摘要权重 1）和 `weak_keywords`（弱信号，
  只有四类强词全不中时才启用，把边缘文章尽量收进四大板块），中英文词表都有。
- 新增研究方向（如“翻译地理学”“口述史”）：往对应类的词表里加中英文术语即可；
- 某篇明显该归 A 类却进了 B 类：把该文标题里的标志性术语加进 A 类 `keywords`；
- 开启 LLM 后以 AI 归类为准，规则只在 LLM 失败/未配置时兜底。

## 关键词规则与其他学科

- `keywords_any` = 命中任一即可；`keywords_all` = 必须全部出现；
  `keywords_exclude` = 命中即排除；英文按词边界匹配（不会把 translation 误匹配到
  translational），中文按子串匹配；短语直接写整句。
- **加国际期刊**：在 <https://portal.issn.org> 搜刊名拿 ISSN，照 Crossref 段格式加一行；
  Crossref 查不到（无 DOI 注册）的 OA 刊改走官网 RSS。
- **理工科**：arXiv 最全，改 `sources.arxiv.categories` 与关键词
  （cs.AI/cs.LG/cs.CV/stat.ML/eess.AS 等，完整列表 <https://arxiv.org/category_taxonomy>）。
- **生物医学**：把 `sources.pubmed.enabled` 改 `true`，term 用
  [PubMed 高级检索](https://pubmed.ncbi.nlm.nih.gov/advanced/) 拼好粘入。
- **其他人文社科**：替换 OpenAlex 术语、Crossref 的 ISSN 表和知网 RSS 代码即可。

## 常见问题

**Q：必须用 Public 仓库吗？**
Public 仓库 Actions 分钟数完全免费且够用；Private 每月也有 2000 分钟免费额度，
这种任务每天一次、每次几分钟，同样够用；密钥无论哪种可见性都存在 Secrets 里，不会泄露。

**Q：为什么 8 点没准时收到？**
GitHub 免费版定时任务在高峰期可能延迟几分钟到几十分钟，属正常现象；
要求准点可改为云函数（如腾讯云 SCF）或本地任务计划，逻辑完全一样。

**Q：会重复推送同一篇吗？**
不会。程序用 `data/seen.json` 记录推过的论文（DOI/arXiv ID/“刊名+归一化标题”），
每次跑完自动 commit 回仓库；知网链接里的动态参数不参与去重，同一篇不会因链接变化重推。

**Q：某一天没收到？**
先看 Actions 日志。常见原因：① 当天确实没有新论文（想收“平安信”就保持
`runtime.empty_notify: true`）；② 渠道密钥填错或过期；③ 某个数据源临时抽风，
日志会标明失败源，单源失败被隔离，不影响其他源。

**Q：想一天推两次 / 改时间？**
改 `.github/workflows/daily.yml` 里的 cron（UTC 时间，北京时间减 8 小时）。
例如 `'0 0,12 * * *'` 是北京 8:00 和 20:00；`'30 1 * * *'` 是北京 9:30。

**Q：第一次运行怎么推了几十篇？**
首次运行要覆盖整个时间窗（知网双月刊窗口 60–90 天、Crossref 21 天、OpenAlex 7 天），
属于正常现象；第二天起只推真正新增，通常每天几篇到十几篇。

**Q：OpenAlex/综合刊里偶尔出现不太相关的论文？**
跨刊关键词扫描天然有少量边缘命中。降噪手段：① 收紧该源的 `keywords_any` 或往
`keywords_exclude` 加假阳性词；② 启用 LLM 并设 `only_recommended: true`，
只推模型评分 7 分以上的文章。翻译专刊“锁刊全收”路不受此影响。

**Q：想追踪多个不相关主题？**
在同一个源里把各主题代表词都放进关键词列表（任一命中），
或复制整个工程建第二个仓库、用不同配置独立推送。

---

问题排查顺序：Actions 运行日志 → `data/reports/` 里当天日报是否生成 → 密钥名字与渠道开关。
