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