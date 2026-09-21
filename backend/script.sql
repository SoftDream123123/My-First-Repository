-- ============================================================================
-- AI 智能面试助手 —— 建库建表脚本
--
-- 用法：
--     mysql -uroot -p --default-character-set=utf8mb4 < script.sql
--
-- 覆盖范围：MVP-1 + MVP-2 + MVP-3，共 15 张表。
--
--     §1  建库
--     §2  建表            —— 空库直接跑这一节（全新安装）
--     §3  存量库升级      —— 已有 MVP-1 库才需要，**默认整段注释掉**
--     §4  与 Alembic 对齐
--     §5  推倒重建        —— 默认注释掉，会丢数据
--
-- ---------------------------------------------------------------------------
-- 本批次（MVP-2 / MVP-3）的 schema 事实来源
--
--     按项目约定，这两批**只改模型、不写 Alembic 迁移**（PRD §11）。因此本文件
--     与 `backend/app/**/models.py` 才是当前 schema 的事实来源，而非 alembic/versions/。
--     Alembic 目前停在 b7f1c2a4d8e6（user.role 加 candidate 取值），其后的结构变更
--     （6 张新表、9 个新列、1 处枚举扩值）都不在迁移里。
--
--     本脚本的 DDL 由模型**编译得到**（不是手抄），列序 / 类型 / 可空性 / 索引 /
--     外键与模型逐项对应。改动模型后必须回头同步本文件。
-- ---------------------------------------------------------------------------
--
-- 关于约束命名：名字由 MySQL 按以下规则生成，与人手写的一致，故一律**不写名字**：
--     · 外键            → <表名>_ibfk_<N>，N 由定义顺序决定，故同表内顺序需与模型一致
--     · 单列唯一键      → 直接取列名（answer.interview_question_id、report.interview_id）
-- 模型里显式命名的（uq_*/ix_*）这里照写。
--
-- ⚠️ 一处已知且刻意的差异（只差名字，语义一致）：
--     本批次模型调整过外键的**声明顺序** —— interview 现在是
--     position_id → resume_id → created_by，question 是 position_id → created_by。
--     而 dev 库这两个表是 MVP-1 迁移建的，那边 created_by 排在前面。于是：
--         · 本脚本建出的 interview / question 的 ibfk 编号 = 模型 = 测试库的编号
--         · dev 库这两个表的 ibfk 编号 = 旧顺序
--     两者只差外键名，列与约束语义完全一致。以模型为准，不回头迁就旧编号。
--
-- 关于时间默认值：这里写作 DEFAULT (now())，**括号不能省**。
-- 三种写法都合法，但 MySQL 的存储与语义并不相同（实测 MySQL 9.7）：
--     DEFAULT CURRENT_TIMESTAMP  入库即归一化为 CURRENT_TIMESTAMP
--     DEFAULT now()              同上（now() 是 CURRENT_TIMESTAMP 的同义词）
--     DEFAULT (now())            带括号即「表达式默认值」(MySQL 8.0.13+)，
--                                入库存为 now()
-- 既有库（迁移建的）存的就是第三种，故这里也用第三种 —— 否则 schema 比对会出现
-- 十余处「写法不同、行为相同」的假差异，长期会淹没真正的差异。
--
-- 关于 JSON 列：**一律不能写 DEFAULT**。MySQL 的 JSON 列不支持字面量默认值，
-- 写了直接语法报错。默认值只在模型层给（default=list），实际写入永远显式供值。
--
-- 关于 updated_at：只写 DEFAULT (now())，**不加 ON UPDATE CURRENT_TIMESTAMP**。
-- 本项目已定：updated_at 由 ORM 的 onupdate 维护（report.updated_at、resume.updated_at
-- 皆如此），DDL 保持与模型编译结果一致。
--
-- 注意：本脚本只建结构，不写数据。
--       初始管理员请用 `python scripts/seed_admin.py` 创建 —— 密码需经
--       bcrypt 哈希，且不应把凭据硬编码进随代码提交的 SQL 里。
--
-- 若在已有库上执行：§2 的建表语句未加 IF NOT EXISTS，表已存在时会**明确报错**
-- 而不是静默跳过。静默跳过会让「表定义已变更」被掩盖，报错更安全。
-- 已有 MVP-1 库请走 §3，而不是把 §2 再跑一遍。
-- ============================================================================

SET NAMES utf8mb4;

-- ---------------------------------------------------------------------------
-- §1 建库
--    utf8mb4 + utf8mb4_unicode_ci：题目与评语含中文，且候选人姓名/回答可能出现
--    生僻字与 emoji，utf8mb3 存不下。排序规则与测试库保持一致（tests/conftest.py）。
-- ---------------------------------------------------------------------------
CREATE DATABASE IF NOT EXISTS `interview_dev`
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

USE `interview_dev`;


-- ---------------------------------------------------------------------------
-- §2 建表
--    顺序即外键依赖顺序：被引用者必须先存在。
--    user → position → resume → question → interview
--         → interview_question → answer → interview_invitation → interview_prep
--         → question_score → dimension_score → report → candidate_feedback
--         → practice_session → practice_item
-- ---------------------------------------------------------------------------

-- auth 模块 -----------------------------------------------------------------
-- 用户不做物理删除，只置 is_active = 0：position / question / interview 均通过
-- created_by 关联本表，物理删除会造成外键悬空。故外键一律 ON DELETE RESTRICT。
-- role 三种取值：admin / hr / candidate（candidate 由 MVP-2 引入）。
CREATE TABLE `user` (
  `id`            BIGINT       NOT NULL AUTO_INCREMENT,
  `username`      VARCHAR(50)  NOT NULL,
  `password_hash` VARCHAR(255) NOT NULL COMMENT 'bcrypt 哈希，绝不存明文',
  `role`          ENUM('admin','hr','candidate') NOT NULL DEFAULT 'hr',
  `is_active`     BOOL         NOT NULL DEFAULT 1,
  `created_at`    DATETIME     NOT NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  UNIQUE KEY `ix_user_username` (`username`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- position 模块 -------------------------------------------------------------
-- evaluation_dimensions 是 JSON 数组（如 ["沟通能力","专业能力"]）。
-- 维度以**字符串**而非外键存储，与 dimension_score.dimension 同处一个命名空间 ——
-- 评估打分时可直接按维度名归集，无需联表。
CREATE TABLE `position` (
  `id`                    BIGINT       NOT NULL AUTO_INCREMENT,
  `name`                  VARCHAR(100) NOT NULL,
  `jd`                    TEXT         NOT NULL COMMENT '岗位描述',
  `evaluation_dimensions` JSON         NOT NULL,
  `created_by`            BIGINT       NOT NULL,
  `created_at`            DATETIME     NOT NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  -- 同一 HR 下岗位名唯一；不同 HR 可各自维护同名岗位
  UNIQUE KEY `uq_position_owner_name` (`created_by`,`name`),
  KEY `ix_position_created_by` (`created_by`),
  FOREIGN KEY (`created_by`) REFERENCES `user` (`id`) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- resume 模块（MVP-3）-------------------------------------------------------
-- 简历只存纯文本，不存原文件、也不存解析产物，故不存在解析失败分支（PRD §1.3）。
-- content 用 TEXT：正文上限 20000 字符由服务层护栏承担（已超 VARCHAR 的实用上限）。
--
-- 写入方**只有候选人**，created_by 恒为候选人用户 id（PRD §4.10）。HR 的读取权限
-- 不在本表判定，而在「该简历是否关联到自己名下的某场面试」上判定 —— 判据由
-- interview 实现，本表只提供无权限过滤的读取。
--
-- 刻意**不加** (created_by, title) 唯一约束：候选人留两份都叫「通用简历」是无害的
-- 用法（与 position 的 uq_position_owner_name 不同，岗位名是检索键，简历标题不是）。
CREATE TABLE `resume` (
  `id`                BIGINT       NOT NULL AUTO_INCREMENT,
  `title`             VARCHAR(100) NOT NULL,
  `content`           TEXT         NOT NULL COMMENT '纯文本正文，上限 20000 字符由服务层校验',
  `candidate_name`    VARCHAR(100) NULL,
  `candidate_contact` VARCHAR(200) NULL,
  `created_by`        BIGINT       NOT NULL COMMENT '恒为候选人用户 id',
  `created_at`        DATETIME     NOT NULL DEFAULT (now()),
  `updated_at`        DATETIME     NOT NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  KEY `ix_resume_created_by` (`created_by`),
  -- RESTRICT：被面试或练习关联的简历不可删，由服务层转成 409（PRD §4.10）
  FOREIGN KEY (`created_by`) REFERENCES `user` (`id`) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- question 模块（题库）------------------------------------------------------
-- 同一张表同时服务两条业务线：HR 出题抽取与候选人刷题取题，不另建练习题库。
--
-- tags / options 为 JSON 数组；MySQL 的 JSON 列**不允许 DEFAULT**，因此这里没有
-- 默认值 —— ORM 侧的 default=list 会保证插入时总是带上一个值。
CREATE TABLE `question` (
  `id`          BIGINT      NOT NULL AUTO_INCREMENT,
  `position_id` BIGINT      NOT NULL,
  `category`    VARCHAR(50) NOT NULL DEFAULT '通用',
  `dimension`   VARCHAR(50) NOT NULL COMMENT '考察维度，与 position.evaluation_dimensions 同名',
  `content`     TEXT        NOT NULL,
  `difficulty`  ENUM('easy','medium','hard') NOT NULL DEFAULT 'medium',
  `tags`        JSON        NOT NULL,
  -- ---- 刷题相关字段（MVP-2，PRD §4.3）----
  -- 默认简答：存量题目全部是纯文本题，按「简答」理解才符合事实。
  -- 默认单选会凭空造出无选项的单选题。
  `question_type`    ENUM('single_choice','short_answer') NOT NULL DEFAULT 'short_answer',
  -- 选项不建独立表：它是题目的从属属性，量级小（≤10）且无需跨题查询
  `options`          JSON        NOT NULL COMMENT '单选题的选项列表，简答题为空数组',
  -- 允许为 NULL：存量题目没有答案，且存在「先有题、后有答案」的中间态
  -- （AI 生成后由 HR 确认）。若给空串默认值会把「未填写」与「故意留空」混为一谈。
  `reference_answer` TEXT        NULL,
  `explanation`      TEXT        NULL,
  `source`      ENUM('bank','ai') NOT NULL DEFAULT 'bank',
  `created_by`  BIGINT      NOT NULL,
  `created_at`  DATETIME    NOT NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  KEY `ix_question_created_by` (`created_by`),
  KEY `ix_question_dimension` (`dimension`),
  -- 出题取数的主查询路径：按岗位圈定范围，再按归属过滤（数据隔离）
  KEY `ix_question_position_owner` (`position_id`,`created_by`),
  KEY `ix_question_source` (`source`),
  -- 刷题按题型取题（PRD §4.7）
  KEY `ix_question_type` (`question_type`),
  FOREIGN KEY (`position_id`) REFERENCES `position` (`id`) ON DELETE RESTRICT,
  FOREIGN KEY (`created_by`)  REFERENCES `user` (`id`)     ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- interview 模块 ------------------------------------------------------------
-- status 状态机（PRD §5.1）：
--     draft → ongoing → completed → evaluating → evaluated
-- 迁移合法性由 service 层集中校验，数据库只约束取值范围。
-- 用 ENUM 而非 VARCHAR：非法状态在写入时即被拒绝，不必等业务层发现。
--
-- resume_id **由候选人侧写入**（PRD §4.13），不是 HR 创建面试时写入：简历由候选人
-- 提交，时间上晚于创建面试，因此创建面试的请求体不接受 resume_id。
-- RESTRICT 而非 SET NULL：SET NULL 会让「简历被删 → 面试静默失去简历」而不报错；
-- RESTRICT 让删除方（候选人）收到 409 自行决定。
CREATE TABLE `interview` (
  `id`                BIGINT       NOT NULL AUTO_INCREMENT,
  `position_id`       BIGINT       NOT NULL,
  `candidate_name`    VARCHAR(100) NOT NULL,
  `candidate_contact` VARCHAR(200) NULL,
  `resume_id`         BIGINT       NULL COMMENT '候选人关联到本场的简历，未关联为 NULL',
  `status`            ENUM('draft','ongoing','completed','evaluating','evaluated')
                      NOT NULL DEFAULT 'draft',
  `created_by`        BIGINT       NOT NULL,
  `created_at`        DATETIME     NOT NULL DEFAULT (now()),
  `completed_at`      DATETIME     NULL,
  PRIMARY KEY (`id`),
  KEY `ix_interview_created_by` (`created_by`),
  KEY `ix_interview_status` (`status`),
  FOREIGN KEY (`position_id`) REFERENCES `position` (`id`) ON DELETE RESTRICT,
  FOREIGN KEY (`resume_id`)   REFERENCES `resume` (`id`)   ON DELETE RESTRICT,
  FOREIGN KEY (`created_by`)  REFERENCES `user` (`id`)     ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- interview_question（面试题）-----------------------------------------------
-- 三个快照字段是历史面试自洽的前提，出题时一次性写入：
--     content_snapshot   题干 —— 题库改题后，历史面试的题目表述不变
--     dimension_snapshot 考察维度 —— 岗位维度改名后，评估归集不会错位
--     source_snapshot    来源 —— 题库题目被删除后，仍可还原出处
-- question_id 仍保留 RESTRICT 外键：快照保证了内容自洽，但题目本身不该被删掉。
--
-- source_snapshot 含 resume_match（MVP-3）：按候选人简历从题库匹配而来（PRD §4.14）。
-- match_reason（MVP-3）存 AI 给出的匹配理由，与 source_snapshot='resume_match'
-- **成对出现**：非匹配来源的题恒为 NULL。两个事实并存，「有没有理由」与
-- 「是不是匹配来的」不会漂移（PRD §5.2）。
CREATE TABLE `interview_question` (
  `id`                 BIGINT      NOT NULL AUTO_INCREMENT,
  `interview_id`       BIGINT      NOT NULL,
  `question_id`        BIGINT      NOT NULL,
  `seq`                INT         NOT NULL COMMENT '题目顺序，从 1 开始',
  `content_snapshot`   TEXT        NOT NULL,
  `dimension_snapshot` VARCHAR(50) NOT NULL,
  `source_snapshot`    ENUM('bank','ai','resume_match') NOT NULL,
  `match_reason`       TEXT        NULL COMMENT 'AI 给出的匹配理由，仅 resume_match 来源非空',
  `created_at`         DATETIME    NOT NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_interview_question_seq` (`interview_id`,`seq`),
  KEY `ix_interview_question_interview` (`interview_id`),
  KEY `ix_interview_question_question` (`question_id`),
  -- 面试被删时其题目列表一并删除，故 CASCADE
  FOREIGN KEY (`interview_id`) REFERENCES `interview` (`id`) ON DELETE CASCADE,
  FOREIGN KEY (`question_id`)  REFERENCES `question` (`id`)  ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- answer（候选人回答）-------------------------------------------------------
-- 两条作答通道（HR 手工录入 / 候选人在线作答）**共用本表**，用三列表达来源：
--     source       作答**最初**从哪条通道进来（HR 覆盖后仍保留 candidate）
--     answered_by  **最后修改者**
--     submitted_at 候选人**交卷**时刻；HR 手工录入时为 NULL
-- source 与 answered_by 语义不同、不可合并：HR 覆盖候选人作答后
-- source='candidate' 而 answered_by=HR，两个事实都需要保留（PRD §5.2）。
--
-- 唯一键落在 interview_question.id 上，而非 (interview_id, question_id)：
-- 前者直接表达「一道面试题一条回答」，且不妨碍「同一道题库题在一次面试中
-- 出现两次」这一扩展。
--
-- 刻意**不加 is_locked**：「候选人能否改」由 submitted_at 是否为空推导。
-- 两个字段表达同一状态必然漂移。
CREATE TABLE `answer` (
  `id`                    BIGINT   NOT NULL AUTO_INCREMENT,
  `interview_question_id` BIGINT   NOT NULL,
  `content`               TEXT     NOT NULL,
  `source`                ENUM('hr','candidate') NOT NULL DEFAULT 'hr',
  -- 允许为 NULL：迁移前的数据无法倒推修改者。空值表示未知，比编造一个值更诚实。
  `answered_by`           BIGINT   NULL,
  `submitted_at`          DATETIME NULL,
  `recorded_at`           DATETIME NOT NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  -- 唯一键落在 interview_question_id 上，故不另起名字 —— 与模型的产出一致
  UNIQUE KEY (`interview_question_id`),
  FOREIGN KEY (`interview_question_id`) REFERENCES `interview_question` (`id`) ON DELETE CASCADE,
  FOREIGN KEY (`answered_by`)           REFERENCES `user` (`id`)               ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- interview_invitation（作答邀请码，MVP-2）-----------------------------------
-- 与面试状态机**解耦**：候选人作答只是输入通道，不进入面试状态机（PRD §5.1）。
--
-- status 只存三个**终态**取值；`expired` 是读取时派生的，不落库 —— 用定时任务刷
-- 过期状态需要调度器（违反单机约束），且进程不常驻时状态会滞后失真。
--
-- **邀请码明文存储**：HR 需要在系统内展示与复制（PRD §1.3）。若只存哈希，生成时能
-- 显示一次、之后列表页就再也拿不到 —— 与 PRD 直接冲突。缓解措施：128 位熵、
-- 有效期默认 7 天、一次性接受、可随时撤销、候选人侧接口不泄露面试是否存在。
-- 代价是「数据库泄露即邀请泄露」。
CREATE TABLE `interview_invitation` (
  `id`                BIGINT      NOT NULL AUTO_INCREMENT,
  `interview_id`      BIGINT      NOT NULL,
  `code`              VARCHAR(64) NOT NULL COMMENT '明文邀请码，需可重复展示',
  `candidate_user_id` BIGINT      NULL COMMENT '候选人接受后写入；未接受为 NULL',
  `status`            ENUM('pending','accepted','revoked') NOT NULL DEFAULT 'pending',
  `expires_at`        DATETIME    NOT NULL,
  `accepted_at`       DATETIME    NULL,
  `created_by`        BIGINT      NOT NULL,
  `created_at`        DATETIME    NOT NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_interview_invitation_code` (`code`),
  KEY `ix_interview_invitation_interview` (`interview_id`),
  KEY `ix_interview_invitation_candidate` (`candidate_user_id`),
  FOREIGN KEY (`interview_id`)      REFERENCES `interview` (`id`) ON DELETE CASCADE,
  FOREIGN KEY (`candidate_user_id`) REFERENCES `user` (`id`)      ON DELETE RESTRICT,
  FOREIGN KEY (`created_by`)        REFERENCES `user` (`id`)      ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- interview_prep（面试前准备提纲，MVP-3，PRD §4.11）--------------------------
-- **一场面试唯一**（interview_id 加唯一约束）：重新生成即覆盖，不做版本历史。
-- 用唯一约束而不是「查询时取最新」，让「不可能有两条」成为数据库事实。
--
-- **不进入面试状态机**：它是面试开始前的工作稿，「已生成 / 已编辑」与面试推进阶段
-- 相互正交。因此只用 generated_at / edited_at 记录事实，面试是否可生成由
-- interview.status 判定（见 service）。
--
-- **不放 created_by**：能读写它的只有面试的拥有者，而面试本身已有 created_by。
-- 再加一列会引入「两个 created_by 不一致怎么办」的伪问题。
--
-- edited_at 在 AI 重新生成时置回 NULL ——「重新生成」意味着此前的编辑已被整体覆盖，
-- 留着旧值会让界面显示「已手工编辑」而内容其实是 AI 的。
CREATE TABLE `interview_prep` (
  `id`            BIGINT   NOT NULL AUTO_INCREMENT,
  `interview_id`  BIGINT   NOT NULL,
  -- 三个 JSON 列 NOT NULL：三部分**要么都有要么都没有**（ai 层的契约是
  -- 「任一为空即整批失败」）。允许 NULL 会引入「有记录但某部分缺失」这一无意义状态。
  -- ⚠️ 同样不能写 DEFAULT（MySQL 的 JSON 列限制），写入时显式供值。
  `outline`       JSON     NOT NULL,
  `focus_points`  JSON     NOT NULL,
  `question_plan` JSON     NOT NULL,
  `generated_at`  DATETIME NOT NULL COMMENT '最近一次 AI 生成时刻',
  `edited_at`     DATETIME NULL COMMENT '最近一次 HR 手工编辑时刻；重新生成后置回 NULL',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_interview_prep_interview` (`interview_id`),
  FOREIGN KEY (`interview_id`) REFERENCES `interview` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- evaluation 模块 -----------------------------------------------------------
-- 评分一律 DECIMAL(3,1)（0.0–10.0），定点而非浮点：
-- 逐题分要参与求平均算总分，FLOAT/DOUBLE 的舍入误差会累积到报告里。

-- 逐题评分
CREATE TABLE `question_score` (
  `id`                    BIGINT       NOT NULL AUTO_INCREMENT,
  `interview_id`          BIGINT       NOT NULL,
  `interview_question_id` BIGINT       NOT NULL,
  `score`                 DECIMAL(3,1) NOT NULL,
  `comment`               TEXT         NOT NULL,
  `created_at`            DATETIME     NOT NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_question_score_interview_entry` (`interview_id`,`interview_question_id`),
  KEY `ix_question_score_interview` (`interview_id`),
  FOREIGN KEY (`interview_id`)          REFERENCES `interview` (`id`)          ON DELETE CASCADE,
  FOREIGN KEY (`interview_question_id`) REFERENCES `interview_question` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
-- 说明：interview_id 与 interview_question_id 存在传递依赖，此处的冗余是刻意的。
-- 「清空某场面试的全部评分」与「按面试查询评分」是最高频操作，冗余这一列让二者免于联表。

-- 多维评分（供雷达图）
CREATE TABLE `dimension_score` (
  `id`           BIGINT       NOT NULL AUTO_INCREMENT,
  `interview_id` BIGINT       NOT NULL,
  `dimension`    VARCHAR(50)  NOT NULL,
  `score`        DECIMAL(3,1) NOT NULL,
  `comment`      TEXT         NOT NULL,
  `created_at`   DATETIME     NOT NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  -- 一场面试的同一维度只应有一行；重评时先清后写
  UNIQUE KEY `uq_dimension_score_interview_dim` (`interview_id`,`dimension`),
  KEY `ix_dimension_score_interview` (`interview_id`),
  FOREIGN KEY (`interview_id`) REFERENCES `interview` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 汇总报告。一次面试一份，故 interview_id 唯一（同时充当查询索引）。
-- strengths / weaknesses 为 JSON 数组，同样无默认值（MySQL JSON 列限制）。
CREATE TABLE `report` (
  `id`            BIGINT       NOT NULL AUTO_INCREMENT,
  `interview_id`  BIGINT       NOT NULL,
  `overall_score` DECIMAL(3,1) NOT NULL,
  `conclusion`    TEXT         NOT NULL,
  `strengths`     JSON         NOT NULL,
  `weaknesses`    JSON         NOT NULL,
  `created_at`    DATETIME     NOT NULL DEFAULT (now()),
  `updated_at`    DATETIME     NOT NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  -- 同上：唯一键名由 MySQL 取列名，与模型的产出一致
  UNIQUE KEY (`interview_id`),
  FOREIGN KEY (`interview_id`) REFERENCES `interview` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
-- 说明：updated_at 在 ORM 层由 onupdate 维护；此处不加 ON UPDATE CURRENT_TIMESTAMP，
-- 以与模型编译结果保持一致（模型是 schema 的事实来源）。

-- 面向候选人的脱敏反馈（MVP-2）
-- 为什么独立成表而不是给 report 加列：两份文本**受众不同、可见性规则不同**。
-- 混在一张表里，report 的任何读取路径（含 HR 报告接口）都可能不小心把候选人字段
-- 带出去；独立成表让可见性边界落在**表**这一层 —— HR 报告接口结构上读不到候选人
-- 字段，report 的 schema 也完全不动，直接满足 PRD §4.9「HR 端报告视图保持不变」。
--
-- 两点刻意的缺失：
--   · **不设 updated_at**：反馈的输入就是报告，报告重评即整行重建。支持「更新」就
--     必须回答「哪部分过期了」；整行删除重建把这个问题消掉。
--   · **不存总分**：总分属「评估结果」而非「候选人文案」。存储层与可见性层解耦后，
--     改档位配置 CANDIDATE_FEEDBACK_LEVEL **不需要重新生成反馈**。
CREATE TABLE `candidate_feedback` (
  `id`           BIGINT   NOT NULL AUTO_INCREMENT,
  `interview_id` BIGINT   NOT NULL,
  `conclusion`   TEXT     NOT NULL COMMENT '面向本人的重写，不含去留判断（PRD §4.9）',
  `strengths`    JSON     NOT NULL,
  `weaknesses`   JSON     NOT NULL,
  `generated_at` DATETIME NOT NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  -- 一场面试唯一；并发首次生成由它兜底
  UNIQUE KEY `uq_candidate_feedback_interview` (`interview_id`),
  -- 这个普通索引与上面的唯一键在功能上重复，但**模型里确实声明了它**，故照写 ——
  -- 脚本的契约是与模型逐项对应，不替模型做优化决定。要去掉它应当改模型，
  -- 而不是只在这里少写一行（否则脚本建出的库与测试库对不上）。
  KEY `ix_candidate_feedback_interview` (`interview_id`),
  FOREIGN KEY (`interview_id`) REFERENCES `interview` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- practice 模块（MVP-2 + MVP-3）---------------------------------------------
-- 两张表都**不与 interview 发生任何关系** —— 刷题是独立的业务线（PRD §9），
-- 因此 practice ↔ interview 不存在循环依赖。

-- 练习会话
-- 筛选条件在会话上留痕 —— 否则无法回答「这次练的是哪类题」。
-- position_id 允许 NULL：不选岗位就是「全库随机刷题」，这是刷题的常见用法，
-- 设为 NOT NULL 会强迫候选人先选岗位。
CREATE TABLE `practice_session` (
  `id`                   BIGINT      NOT NULL AUTO_INCREMENT,
  `candidate_user_id`    BIGINT      NOT NULL COMMENT '练习归属 —— 候选人数据隔离的依据',
  `position_id`          BIGINT      NULL,
  -- resume_id（MVP-3）：本次练习关联的简历；NULL = 未关联（绝大多数练习如此）。
  -- RESTRICT 而非 SET NULL：被练习关联的简历不可删除（409 依赖它），SET NULL 会让
  -- 历史练习静默失去「这次是按哪份简历推荐的」这一事实。
  `resume_id`            BIGINT      NULL,
  -- 本次**是否真的**用 AI 按简历选排了题目。
  -- 它不是 resume_id 的冗余：resume_id 非空**不代表**真的按简历推荐了 —— AI 可能
  -- 失败或未命中，此时已降级为普通筛选（PRD §7）。两个字段回答两个不同问题：
  -- 「候选人想用哪份简历」vs「系统实际做到了没有」。合并会让降级变成**静默**：
  -- 候选人关联了简历却拿到一堆通用题，界面上没有任何解释，只能认为功能坏了。
  `resume_match_applied` BOOL        NOT NULL DEFAULT 0,
  `category`             VARCHAR(50) NULL,
  `dimension`            VARCHAR(50) NULL,
  `difficulty`           ENUM('easy','medium','hard') NULL,
  `question_type`        ENUM('single_choice','short_answer') NULL,
  `status`               ENUM('ongoing','finished') NOT NULL DEFAULT 'ongoing',
  `total`                INT         NOT NULL,
  -- 两个计数**每次提交后重算**，不累加 —— 同一题可重复提交（错题重练是正当用法），
  -- 累加会让计数超过 total。重算永远等于事实。
  `answered_count`       INT         NOT NULL DEFAULT 0,
  `correct_count`        INT         NOT NULL DEFAULT 0,
  `started_at`           DATETIME    NOT NULL DEFAULT (now()),
  `finished_at`          DATETIME    NULL,
  PRIMARY KEY (`id`),
  KEY `ix_practice_session_candidate` (`candidate_user_id`),
  KEY `ix_practice_session_status` (`status`),
  FOREIGN KEY (`candidate_user_id`) REFERENCES `user` (`id`)     ON DELETE RESTRICT,
  FOREIGN KEY (`position_id`)       REFERENCES `position` (`id`) ON DELETE RESTRICT,
  FOREIGN KEY (`resume_id`)         REFERENCES `resume` (`id`)   ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 待答项 —— 会话开始时即按筛选条件生成，并写满题目快照。
-- 题目快照让题库后续删改不影响进行中与历史练习的复看与判分；逐题提交只回填
-- user_answer / is_correct / score / explanation / answered_at。
--
-- 两个快照字段是**刻意补充**的（PRD §5.2 未列）：
--   dimension_snapshot  不加则按维度统计只能联表读 question.dimension，
--                       题库改维度后历史练习的统计会跟着漂移
--   question_type       不加则判分分支要联表读当前值；若 HR 在会话开始后把题从
--                       简答改成单选，已有的空 options_snapshot 会与「单选」分支
--                       冲突，判分直接崩
CREATE TABLE `practice_item` (
  `id`                        BIGINT      NOT NULL AUTO_INCREMENT,
  `session_id`                BIGINT      NOT NULL,
  `question_id`               BIGINT      NOT NULL,
  `seq`                       INT         NOT NULL,
  `content_snapshot`          TEXT        NOT NULL,
  `options_snapshot`          JSON        NOT NULL,
  `reference_answer_snapshot` TEXT        NULL COMMENT '存量题目可能没有参考答案',
  `dimension_snapshot`        VARCHAR(50) NOT NULL,
  `question_type`             ENUM('single_choice','short_answer') NOT NULL,
  -- NULL 表示**尚未提交**（与「提交了空串」不同）
  `user_answer`               TEXT        NULL,
  -- **三态**：TRUE 判对 / FALSE 判错 / NULL 未判分。
  -- NULL 是「未判分」这一独立事实（无参考答案，或 AI 判分失败），与「判错」语义
  -- 完全不同 —— 错题本不能把未判分的题算进去，正确率的分母也不含它。
  -- 加一个 is_scored 布尔表达同一事实只会让两个字段漂移。
  -- ⚠️ 因此它**必须可空**，改成 NOT NULL 会让「未判分」状态消失。
  `is_correct`                BOOL        NULL,
  `score`                     DECIMAL(3,1) NULL,
  `explanation`               TEXT        NULL,
  `answered_at`               DATETIME    NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_practice_item_seq` (`session_id`,`seq`),
  KEY `ix_practice_item_session` (`session_id`),
  KEY `ix_practice_item_question` (`question_id`),
  -- 服务于错题本派生查询（错题本不建表，由 is_correct=false 派生）
  KEY `ix_practice_item_correct` (`is_correct`),
  FOREIGN KEY (`session_id`)  REFERENCES `practice_session` (`id`) ON DELETE CASCADE,
  FOREIGN KEY (`question_id`) REFERENCES `question` (`id`)         ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ---------------------------------------------------------------------------
-- §3 存量库升级（MVP-1 库 → 当前结构）
--
-- ⚠️ 本段**默认整段注释掉**。只有「库里已经是 MVP-1 的 9 张表、且有数据不想丢」
--    时才需要；空库请直接跑 §2，不要跑这里。两段不可同时执行。
--
-- 本段对应 docs/tests/2026-09-21-DDL统一收口清单.md 的操作；那个文件是逐项论证，
-- 这里是可直接执行的形态。
--
-- 执行顺序（外键依赖决定，不可调换）：
--     步骤 1  建 `resume` 表
--     步骤 2  `interview` 加 resume_id + 外键           → 见 §3.1
--     步骤 3  建其余 5 张表：`interview_invitation` / `interview_prep` /
--             `candidate_feedback` / `practice_session` / `practice_item`
--     步骤 4  三个既有表加列 / 改列                     → 见 §3.2 / §3.3 / §3.4
--
-- 步骤 1 与步骤 3 的建表语句**与 §2 中同名表的段落逐字相同**，这里不再抄一遍
-- （抄一遍就有两处要同步，正是本文件开头要避免的那种漂移）。请直接从 §2 复制
-- 对应的 CREATE TABLE 段落执行 —— 注意 `practice_session` / `practice_item` 在 §2
-- 里已是「建到位的最终形态」（含 MVP-3 的 resume_id / resume_match_applied），
-- 不存在「先按 MVP-2 建、再改」的中间态。
--
-- 存量数据如何自洽（这就是 §3.2 / §3.3 里的默认值与回填存在的理由）：
--     · 46 道存量题无选项 → 回填空数组，题型默认 'short_answer'（存量题都是纯文本题）
--     · 34 条存量作答     → source 默认 'hr'，归到「HR 手工录入」，语义正确
--     · answered_by       → 留 NULL（迁移前的数据无法倒推修改者，空值比编造诚实）
-- ---------------------------------------------------------------------------

-- ---- §3.1 interview：加 resume_id（MVP-3）----
-- ALTER TABLE `interview`
--   ADD COLUMN `resume_id` BIGINT NULL AFTER `candidate_contact`;
-- ALTER TABLE `interview`
--   ADD FOREIGN KEY (`resume_id`) REFERENCES `resume` (`id`) ON DELETE RESTRICT;

-- ---- §3.2 question：加 4 列（MVP-2）----
-- ⚠️ options 必须**三步走**：MySQL 的 JSON 列不支持 DEFAULT，因此无法「加列时给默认
--    值」；既有行会留在 NULL 上，一步到位加 NOT NULL 会直接失败。
-- ALTER TABLE `question`
--   ADD COLUMN `question_type`    ENUM('single_choice','short_answer') NOT NULL DEFAULT 'short_answer' AFTER `tags`,
--   ADD COLUMN `options`          JSON NULL AFTER `question_type`,
--   ADD COLUMN `reference_answer` TEXT NULL AFTER `options`,
--   ADD COLUMN `explanation`      TEXT NULL AFTER `reference_answer`;
-- UPDATE `question` SET `options` = JSON_ARRAY() WHERE `options` IS NULL;
-- ALTER TABLE `question` MODIFY COLUMN `options` JSON NOT NULL;
-- CREATE INDEX `ix_question_type` ON `question` (`question_type`);

-- ---- §3.3 answer：加 3 列（MVP-2）----
-- source 带默认值 'hr'，存量 34 行作答自动归到「HR 手工录入」，语义正确。
-- ALTER TABLE `answer`
--   ADD COLUMN `source`       ENUM('hr','candidate') NOT NULL DEFAULT 'hr' AFTER `content`,
--   ADD COLUMN `answered_by`  BIGINT NULL AFTER `source`,
--   ADD COLUMN `submitted_at` DATETIME NULL AFTER `answered_by`;
-- ALTER TABLE `answer`
--   ADD FOREIGN KEY (`answered_by`) REFERENCES `user` (`id`) ON DELETE RESTRICT;

-- ---- §3.4 interview_question：加 match_reason + 扩 source_snapshot 枚举（MVP-3）----
-- ALTER TABLE `interview_question`
--   ADD COLUMN `match_reason` TEXT NULL AFTER `source_snapshot`;
--
-- ⚠️⚠️ 下面这条是**整次收口最容易漏的一条**，它既不是「新建的表」也不是「新增的列」，
--      而是「**改既有列的取值域**」。按「新增了哪些列 / 表」收集 DDL 时它必然不在名单上。
--      漏掉的后果：按简历补题写入 resume_match 时抛
--      `DataError: Data truncated for column 'source_snapshot'` —— 功能直接不可用，
--      且报错与 DDL 无关，排查成本极高。
--      不改成 VARCHAR：为加一个取值而放开整列约束，会丢掉数据库对「来源」的全部校验。
-- ALTER TABLE `interview_question`
--   MODIFY COLUMN `source_snapshot` ENUM('bank','ai','resume_match') NOT NULL;


-- ---------------------------------------------------------------------------
-- §4 收尾：与 Alembic 对齐
--
-- 本脚本落地的结构**超出** Alembic 当前 head：迁移只到 b7f1c2a4d8e6
-- （user.role 加 candidate），MVP-2 / MVP-3 的表与列按约定没有写迁移。
--
-- 因此若这个库还要用 Alembic 做增量演进，只需让它知道「已经处在 head 版本」，
-- 否则 upgrade head 会重复执行 b7f1c2a4d8e6：
--
--     cd backend
--     python -m alembic stamp head
--
-- 本脚本**不代建 alembic_version 表**：把版本号写死在 SQL 里，一旦新增迁移就会
-- 变成错误声明（声称已应用一个其实没应用的版本），比不写更有害。
-- ---------------------------------------------------------------------------


-- ---------------------------------------------------------------------------
-- §5 推倒重建（默认注释掉 —— 会丢数据，仅在需要全新开始时取消注释）
--
-- SET FOREIGN_KEY_CHECKS = 0;
-- DROP TABLE IF EXISTS `practice_item`;
-- DROP TABLE IF EXISTS `practice_session`;
-- DROP TABLE IF EXISTS `candidate_feedback`;
-- DROP TABLE IF EXISTS `report`;
-- DROP TABLE IF EXISTS `dimension_score`;
-- DROP TABLE IF EXISTS `question_score`;
-- DROP TABLE IF EXISTS `interview_prep`;
-- DROP TABLE IF EXISTS `interview_invitation`;
-- DROP TABLE IF EXISTS `answer`;
-- DROP TABLE IF EXISTS `interview_question`;
-- DROP TABLE IF EXISTS `interview`;
-- DROP TABLE IF EXISTS `question`;
-- DROP TABLE IF EXISTS `resume`;
-- DROP TABLE IF EXISTS `position`;
-- DROP TABLE IF EXISTS `user`;
-- SET FOREIGN_KEY_CHECKS = 1;
-- ---------------------------------------------------------------------------
