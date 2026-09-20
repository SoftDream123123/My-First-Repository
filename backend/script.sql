-- ============================================================================
-- AI 智能面试助手 —— 建库建表脚本
--
-- 用法：
--     mysql -uroot -p --default-character-set=utf8mb4 < script.sql
--
-- 本脚本与 Alembic 迁移 ebfc6ff09bbf（initial schema）**逐列等价**，
-- 是同一套 schema 的两种落地方式：
--     · Alembic  —— 增量演进用，是 schema 的唯一事实来源
--     · 本脚本   —— 一键初始化用，适合交付、评审、给 DBA 过目
-- 两者产生分歧时，以 Alembic 为准，并回来修正本文件。
--
-- 关于约束命名：名字必须与迁移的产出一致，否则「脚本建的库」和「迁移建的库」
-- 会出现两套名字，将来写 drop 型迁移时必然对不上其中一个。规则是照搬 SQLAlchemy
-- 的行为 —— 模型里显式命名的（uq_*/ix_*）这里照写；模型里未命名的（外键、
-- 列上的 unique=True）这里也不写名字，交由 MySQL 生成：
--     · 外键            → <表名>_ibfk_<N>，N 由定义顺序决定，故同表内顺序需与迁移一致
--     · 单列唯一键      → 直接取列名（answer.interview_question_id、report.interview_id）
-- 若确实想让约束有可读名字，正确做法是改 Alembic 迁移，让所有环境一起变。
--
-- 关于时间默认值：这里写作 DEFAULT (now())，**括号不能省**。
-- 三种写法都合法，但 MySQL 的存储与语义并不相同：
--     DEFAULT CURRENT_TIMESTAMP  字面归一化为 CURRENT_TIMESTAMP（同义词写法）
--     DEFAULT now()              同上，也会被归一化
--     DEFAULT (now())            带括号即「表达式默认值」(MySQL 8.0.13+)，
--                                字面保留为 now()
-- 迁移（SQLAlchemy）发的是第三种，所以这里也用第三种 —— 否则 schema 比对会出现
-- 10 处「写法不同、行为相同」的假差异，长期会淹没真正的差异。
--
-- 注意：本脚本只建结构，不写数据。
--       初始管理员请用 `python scripts/seed_admin.py` 创建 —— 密码需经
--       bcrypt 哈希，且不应把凭据硬编码进随代码提交的 SQL 里。
--
-- 若在已有库上执行：建表语句未加 IF NOT EXISTS，表已存在时会**明确报错**
-- 而不是静默跳过。静默跳过会让「表定义已变更」被掩盖，报错更安全。
-- 需要推倒重建时，取消文件末尾 DROP 段的注释。
-- ============================================================================

SET NAMES utf8mb4;

-- ---------------------------------------------------------------------------
-- 1. 建库
--    utf8mb4 + utf8mb4_unicode_ci：题目与评语含中文，且候选人姓名/回答可能出现
--    生僻字与 emoji，utf8mb3 存不下。排序规则与测试库保持一致（tests/conftest.py）。
-- ---------------------------------------------------------------------------
CREATE DATABASE IF NOT EXISTS `interview_dev`
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

USE `interview_dev`;


-- ---------------------------------------------------------------------------
-- 2. 建表
--    顺序即外键依赖顺序：被引用者必须先存在。
--    user → position → interview → question → interview_question
--         → answer / dimension_score / question_score / report
-- ---------------------------------------------------------------------------

-- auth 模块 -----------------------------------------------------------------
-- 用户不做物理删除，只置 is_active = 0：position / question / interview 均通过
-- created_by 关联本表，物理删除会造成外键悬空。故外键一律 ON DELETE RESTRICT。
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


-- interview 模块 ------------------------------------------------------------
-- status 状态机（PRD §5.1）：
--     draft → ongoing → completed → evaluating → evaluated
-- 迁移合法性由 service 层集中校验，数据库只约束取值范围。
-- 用 ENUM 而非 VARCHAR：非法状态在写入时即被拒绝，不必等业务层发现。
CREATE TABLE `interview` (
  `id`                BIGINT       NOT NULL AUTO_INCREMENT,
  `position_id`       BIGINT       NOT NULL,
  `candidate_name`    VARCHAR(100) NOT NULL,
  `candidate_contact` VARCHAR(200) NULL,
  `status`            ENUM('draft','ongoing','completed','evaluating','evaluated')
                      NOT NULL DEFAULT 'draft',
  `created_by`        BIGINT       NOT NULL,
  `created_at`        DATETIME     NOT NULL DEFAULT (now()),
  `completed_at`      DATETIME     NULL,
  PRIMARY KEY (`id`),
  KEY `ix_interview_created_by` (`created_by`),
  KEY `ix_interview_status` (`status`),
  FOREIGN KEY (`created_by`) REFERENCES `user` (`id`) ON DELETE RESTRICT,
  FOREIGN KEY (`position_id`) REFERENCES `position` (`id`) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- question 模块（题库）------------------------------------------------------
-- tags 为 JSON 数组；MySQL 的 JSON 列**不允许 DEFAULT**，因此这里没有默认值 ——
-- ORM 侧的 default=list 会保证插入时总是带上一个值（通常是空数组）。
CREATE TABLE `question` (
  `id`          BIGINT      NOT NULL AUTO_INCREMENT,
  `position_id` BIGINT      NOT NULL,
  `category`    VARCHAR(50) NOT NULL DEFAULT '通用',
  `dimension`   VARCHAR(50) NOT NULL COMMENT '考察维度，与 position.evaluation_dimensions 同名',
  `content`     TEXT        NOT NULL,
  `difficulty`  ENUM('easy','medium','hard') NOT NULL DEFAULT 'medium',
  `tags`        JSON        NOT NULL,
  `source`      ENUM('bank','ai') NOT NULL DEFAULT 'bank',
  `created_by`  BIGINT      NOT NULL,
  `created_at`  DATETIME    NOT NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  KEY `ix_question_created_by` (`created_by`),
  KEY `ix_question_dimension` (`dimension`),
  -- 出题取数的主查询路径：按岗位圈定范围，再按归属过滤（数据隔离）
  KEY `ix_question_position_owner` (`position_id`,`created_by`),
  KEY `ix_question_source` (`source`),
  FOREIGN KEY (`created_by`) REFERENCES `user` (`id`) ON DELETE RESTRICT,
  FOREIGN KEY (`position_id`) REFERENCES `position` (`id`) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- interview_question（面试题）-----------------------------------------------
-- 三个快照字段是历史面试自洽的前提，出题时一次性写入：
--     content_snapshot   题干 —— 题库改题后，历史面试的题目表述不变
--     dimension_snapshot 考察维度 —— 岗位维度改名后，评估归集不会错位
--     source_snapshot    来源 —— 题库题目被删除后，仍可还原出处
-- question_id 仍保留 RESTRICT 外键：快照保证了内容自洽，但题目本身不该被删掉。
CREATE TABLE `interview_question` (
  `id`                 BIGINT      NOT NULL AUTO_INCREMENT,
  `interview_id`       BIGINT      NOT NULL,
  `question_id`        BIGINT      NOT NULL,
  `seq`                INT         NOT NULL COMMENT '题目顺序，从 1 开始',
  `content_snapshot`   TEXT        NOT NULL,
  `dimension_snapshot` VARCHAR(50) NOT NULL,
  `source_snapshot`    ENUM('bank','ai') NOT NULL,
  `created_at`         DATETIME    NOT NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_interview_question_seq` (`interview_id`,`seq`),
  KEY `ix_interview_question_interview` (`interview_id`),
  KEY `ix_interview_question_question` (`question_id`),
  -- 面试被删时其题目列表一并删除，故 CASCADE
  FOREIGN KEY (`interview_id`) REFERENCES `interview` (`id`) ON DELETE CASCADE,
  FOREIGN KEY (`question_id`) REFERENCES `question` (`id`) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- answer（候选人回答）-------------------------------------------------------
-- 唯一键落在 interview_question.id 上，而非 (interview_id, question_id)：
-- 前者直接表达「一道面试题一条回答」，且不妨碍「同一道题库题在一次面试中
-- 出现两次」这一扩展。
CREATE TABLE `answer` (
  `id`                    BIGINT   NOT NULL AUTO_INCREMENT,
  `interview_question_id` BIGINT   NOT NULL,
  `content`               TEXT     NOT NULL,
  `recorded_at`           DATETIME NOT NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  -- 唯一键落在 interview_question_id 上，故不另起名字 —— 与迁移的产出一致
  UNIQUE KEY (`interview_question_id`),
  FOREIGN KEY (`interview_question_id`) REFERENCES `interview_question` (`id`) ON DELETE CASCADE
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
  FOREIGN KEY (`interview_id`) REFERENCES `interview` (`id`) ON DELETE CASCADE,
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
  -- 同上：唯一键名由 MySQL 取列名，与迁移一致
  UNIQUE KEY (`interview_id`),
  FOREIGN KEY (`interview_id`) REFERENCES `interview` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
-- 说明：updated_at 在 ORM 层由 onupdate 维护；此处不加 ON UPDATE CURRENT_TIMESTAMP，
-- 以与 Alembic 生成的 DDL 保持一致（迁移是 schema 的事实来源）。


-- ---------------------------------------------------------------------------
-- 3. 收尾：与 Alembic 对齐
--
-- 本脚本落地的就是初始迁移 ebfc6ff09bbf 的结构。若后续还要用 Alembic 做增量演进，
-- 必须让 Alembic 知道「这个库已经处在初始版本」，否则 upgrade head 会重复建表：
--
--     cd backend
--     python -m alembic stamp head
--
-- 本脚本**不代建 alembic_version 表**：把版本号写死在 SQL 里，一旦新增迁移就会
-- 变成错误声明（声称已应用一个其实没应用的版本），比不写更有害。
-- ---------------------------------------------------------------------------


-- ---------------------------------------------------------------------------
-- 4. 推倒重建（默认注释掉 —— 会丢数据，仅在需要全新开始时取消注释）
--
-- SET FOREIGN_KEY_CHECKS = 0;
-- DROP TABLE IF EXISTS `report`;
-- DROP TABLE IF EXISTS `dimension_score`;
-- DROP TABLE IF EXISTS `question_score`;
-- DROP TABLE IF EXISTS `answer`;
-- DROP TABLE IF EXISTS `interview_question`;
-- DROP TABLE IF EXISTS `question`;
-- DROP TABLE IF EXISTS `interview`;
-- DROP TABLE IF EXISTS `position`;
-- DROP TABLE IF EXISTS `user`;
-- SET FOREIGN_KEY_CHECKS = 1;
-- ---------------------------------------------------------------------------
