-- website_bazaar_offers
CREATE TABLE IF NOT EXISTS bazaar_offers (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  player_id INT NOT NULL,
  player_name VARCHAR(255) NOT NULL,
  seller_account_id INT NOT NULL,

  status ENUM('active','sold','expired','cancelled') NOT NULL DEFAULT 'active',
  start_time INT UNSIGNED NOT NULL,
  end_time   INT UNSIGNED NOT NULL,

  min_bid   BIGINT UNSIGNED NOT NULL,
  buyout    BIGINT UNSIGNED NULL,
  current_bid BIGINT UNSIGNED NULL,
  current_bidder_account_id INT NULL,

  level INT NOT NULL,
  vocation TINYINT NOT NULL,
  sex TINYINT NOT NULL,

  looktype INT NOT NULL,
  lookhead INT NOT NULL,
  lookbody INT NOT NULL,
  looklegs INT NOT NULL,
  lookfeet INT NOT NULL,

  equipment_json JSON NULL,
  inventory_json JSON NULL,
  depot_json JSON NULL,

  comment TEXT NULL,
  created_at INT UNSIGNED NOT NULL,
  updated_at INT UNSIGNED NOT NULL,

  INDEX idx_status_end (status, end_time),
  INDEX idx_player (player_id),
  INDEX idx_name (player_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- bids history
CREATE TABLE IF NOT EXISTS bazaar_bids (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  offer_id BIGINT NOT NULL,
  bidder_account_id INT NOT NULL,
  amount BIGINT UNSIGNED NOT NULL,
  created_at INT UNSIGNED NOT NULL,
  FOREIGN KEY (offer_id) REFERENCES bazaar_offers(id) ON DELETE CASCADE,
  INDEX idx_offer (offer_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- optional: soft lock so seller can’t play the character during auction
CREATE TABLE IF NOT EXISTS bazaar_locks (
  player_id INT PRIMARY KEY,
  locked_by_account INT NOT NULL,
  locked_at INT UNSIGNED NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- Coins wallet (one row per OT account)
CREATE TABLE IF NOT EXISTS coins_wallet (
  account_id INT PRIMARY KEY,
  balance BIGINT UNSIGNED NOT NULL DEFAULT 0,
  created_at INT UNSIGNED NOT NULL,
  updated_at INT UNSIGNED NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Coins ledger (append-only audit)
CREATE TABLE IF NOT EXISTS coins_ledger (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  account_id INT NOT NULL,
  delta BIGINT NOT NULL,     -- can be negative or positive
  kind ENUM('credit','debit','hold','release','settle','fee','refund') NOT NULL,
  ref  VARCHAR(64) NULL,     -- e.g. "offer:123", "manual", etc.
  note VARCHAR(255) NULL,
  created_at INT UNSIGNED NOT NULL,
  INDEX idx_acct_time (account_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Active coin hold for the highest bidder
CREATE TABLE IF NOT EXISTS bazaar_holds (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  offer_id BIGINT NOT NULL,
  account_id INT NOT NULL,
  amount BIGINT UNSIGNED NOT NULL,
  active TINYINT(1) NOT NULL DEFAULT 1,
  created_at INT UNSIGNED NOT NULL,
  released_at INT UNSIGNED NULL,
  UNIQUE KEY uniq_active_offer (offer_id, active) -- at most ONE active hold per offer
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Bazaar (same as before but amounts are "coins" conceptually)
-- If you already created bazaar_offers earlier, keep it.
ALTER TABLE bazaar_offers
  MODIFY min_bid BIGINT UNSIGNED NOT NULL,
  MODIFY buyout  BIGINT UNSIGNED NULL,
  MODIFY current_bid BIGINT UNSIGNED NULL;

-- DONATE
-- 1) Wallet on the account row
ALTER TABLE `accounts`
  ADD COLUMN `coins` INT UNSIGNED NOT NULL DEFAULT 0
  COMMENT 'Website wallet / donation coins';

-- 2) Minimal transaction log for auditing + double-charge protection
CREATE TABLE IF NOT EXISTS `coin_tx` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `account_id` INT NOT NULL,                -- match type of accounts.id (usually INT signed)
  `coins` INT NOT NULL,
  `method` ENUM('stripe','paypal','pix','admin') NOT NULL,
  `external_id` VARCHAR(191) NOT NULL,      -- Stripe session id, PayPal order id, etc.
  `created_at` INT UNSIGNED NOT NULL,       -- unix epoch (seconds)
  PRIMARY KEY (`id`),
  UNIQUE KEY `uniq_method_ext` (`method`,`external_id`),
  KEY `idx_account_id_created_at` (`account_id`,`created_at`),
  CONSTRAINT `fk_coin_tx_accounts`
    FOREIGN KEY (`account_id`) REFERENCES `accounts`(`id`)
    ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS pix_tx (
  id            BIGINT PRIMARY KEY AUTO_INCREMENT,
  txid          VARCHAR(64) UNIQUE,      -- PSP transaction id or loc id
  account_id    INT NOT NULL,
  pack_id       VARCHAR(32) NOT NULL,
  coins         INT NOT NULL,
  amount        INT NOT NULL,            -- cents
  currency      VARCHAR(3) NOT NULL,     -- 'BRL'
  provider      VARCHAR(32) NOT NULL,
  status        VARCHAR(32) NOT NULL,    -- created|pending|paid|expired|error
  qr_emv        TEXT,                    -- copia-e-cola (EMV)
  qr_base64     LONGTEXT,                -- image (if PSP returns it)
  external_id   VARCHAR(64),             -- PSP payment id
  created_at    INT NOT NULL,
  expires_at    INT,
  UNIQUE KEY unique_provider_ext (provider, external_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS store_orders (
  id            BIGINT AUTO_INCREMENT PRIMARY KEY,
  account_id    INT NOT NULL,
  player_name   VARCHAR(64) DEFAULT NULL, -- optional: force to a specific char
  itemid        INT NOT NULL,
  actionid      INT NOT NULL,
  count         INT NOT NULL DEFAULT 1,
  town_id       INT NOT NULL DEFAULT 1,   -- Thais is commonly town 1; adjust if needed
  method        VARCHAR(32) NOT NULL,     -- 'stripe' | 'paypal' | ...
  txid          VARCHAR(255) NOT NULL,     -- payment or checkout session id
  status        ENUM('pending','delivered','failed') NOT NULL DEFAULT 'pending',
  error_msg     TEXT NULL,
  created_at    INT NOT NULL,
  delivered_at  INT NULL,
  UNIQUE KEY uniq_tx (txid, actionid)     -- idempotency across retries
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


ALTER TABLE accounts ADD COLUMN email VARCHAR(255) NOT NULL DEFAULT '';
ALTER TABLE accounts ADD email varchar(255) CHARACTER SET utf8mb3 COLLATE utf8mb3_general_ci DEFAULT '' NOT NULL;
ALTER TABLE accounts ADD created int DEFAULT 0 NOT NULL;
ALTER TABLE accounts ADD rlname varchar(255) CHARACTER SET utf8mb3 COLLATE utf8mb3_general_ci DEFAULT '' NOT NULL;
ALTER TABLE accounts ADD location varchar(255) CHARACTER SET utf8mb3 COLLATE utf8mb3_general_ci DEFAULT '' NOT NULL;
ALTER TABLE accounts ADD country varchar(3) CHARACTER SET utf8mb3 COLLATE utf8mb3_general_ci DEFAULT '' NOT NULL;
ALTER TABLE accounts ADD web_lastlogin int DEFAULT 0 NOT NULL;
ALTER TABLE accounts ADD web_flags int DEFAULT 0 NOT NULL;
ALTER TABLE accounts ADD email_hash varchar(32) CHARACTER SET utf8mb3 COLLATE utf8mb3_general_ci DEFAULT '' NOT NULL;
ALTER TABLE accounts ADD email_new varchar(255) CHARACTER SET utf8mb3 COLLATE utf8mb3_general_ci DEFAULT '' NOT NULL;
ALTER TABLE accounts ADD email_new_time int DEFAULT 0 NOT NULL;
ALTER TABLE accounts ADD email_code varchar(255) CHARACTER SET utf8mb3 COLLATE utf8mb3_general_ci DEFAULT '' NOT NULL;
ALTER TABLE accounts ADD email_next int DEFAULT 0 NOT NULL;
ALTER TABLE accounts ADD premium_points int DEFAULT 0 NOT NULL;
ALTER TABLE accounts ADD email_verified tinyint(1) DEFAULT 0 NOT NULL;
ALTER TABLE accounts ADD `key` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_general_ci DEFAULT '' NOT NULL;


-- =====================================================
-- GUILDS
-- =====================================================
CREATE TABLE guilds (
  id                INT NOT NULL AUTO_INCREMENT,
  name              VARCHAR(64)  NOT NULL,
  description       TEXT         NULL,
  motd              TEXT         NULL,
  logo_url          VARCHAR(255) NULL,
  creationdata      INT NULL,         -- UNIX timestamp (optional)
  owner_player_id   INT NULL,
  owner_account_id  INT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_guilds_name (name),
  KEY idx_guilds_owner_player (owner_player_id),
  KEY idx_guilds_owner_account (owner_account_id),
  CONSTRAINT fk_guilds_owner_player
    FOREIGN KEY (owner_player_id) REFERENCES players(id)
      ON UPDATE CASCADE ON DELETE SET NULL,
  CONSTRAINT fk_guilds_owner_account
    FOREIGN KEY (owner_account_id) REFERENCES accounts(id)
      ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =====================================================
-- GUILD_RANKS
-- =====================================================
CREATE TABLE guild_ranks (
  id         INT NOT NULL AUTO_INCREMENT,
  guild_id   INT NOT NULL,
  name       VARCHAR(64) NOT NULL,
  `level`    TINYINT NOT NULL DEFAULT 1,
  PRIMARY KEY (id),
  UNIQUE KEY uq_ranks_guild_level (guild_id, `level`),
  UNIQUE KEY uq_ranks_guild_name  (guild_id, name),
  KEY idx_ranks_guild (guild_id),
  CONSTRAINT fk_ranks_guild
    FOREIGN KEY (guild_id) REFERENCES guilds(id)
      ON UPDATE CASCADE ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =====================================================
-- GUILD_MEMBERS
-- =====================================================
CREATE TABLE guild_members (
  id         INT NOT NULL AUTO_INCREMENT,
  guild_id   INT NOT NULL,
  player_id  INT NOT NULL,
  rank_id    INT NULL,
  joined_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_members_unique (guild_id, player_id),
  KEY idx_members_guild (guild_id),
  KEY idx_members_player (player_id),
  KEY idx_members_rank (rank_id),
  CONSTRAINT fk_members_guild
    FOREIGN KEY (guild_id)  REFERENCES guilds(id)
      ON UPDATE CASCADE ON DELETE CASCADE,
  CONSTRAINT fk_members_player
    FOREIGN KEY (player_id) REFERENCES players(id)
      ON UPDATE CASCADE ON DELETE CASCADE,
  CONSTRAINT fk_members_rank
    FOREIGN KEY (rank_id)   REFERENCES guild_ranks(id)
      ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =====================================================
-- GUILD_INVITES
-- =====================================================
CREATE TABLE guild_invites (
  id             INT NOT NULL AUTO_INCREMENT,
  guild_id       INT NOT NULL,
  player_id      INT NOT NULL,
  invited_by_id  INT NULL,
  created_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_invites_unique (guild_id, player_id),
  KEY idx_invites_guild (guild_id),
  KEY idx_invites_player (player_id),
  KEY idx_invites_invited_by (invited_by_id),
  CONSTRAINT fk_invites_guild
    FOREIGN KEY (guild_id)      REFERENCES guilds(id)
      ON UPDATE CASCADE ON DELETE CASCADE,
  CONSTRAINT fk_invites_player
    FOREIGN KEY (player_id)     REFERENCES players(id)
      ON UPDATE CASCADE ON DELETE CASCADE,
  CONSTRAINT fk_invites_invited_by
    FOREIGN KEY (invited_by_id) REFERENCES players(id)
      ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;