ALTER TABLE trades
  ADD COLUMN IF NOT EXISTS exit_reason VARCHAR(30);

ALTER TABLE trades
  ADD COLUMN IF NOT EXISTS entry_atr FLOAT;

ALTER TABLE portfolio
  ADD COLUMN IF NOT EXISTS highest_price FLOAT;

ALTER TABLE portfolio
  ADD COLUMN IF NOT EXISTS entry_atr FLOAT;

INSERT INTO settings (key, value, description)
VALUES ('hard_stop_atr_mult', '2.5', 'ATR 하드 스탑 배수')
     , ('trailing_stop_atr_mult', '2.0', 'ATR 트레일링 스탑 배수')
     , ('max_holding_days', '20', '최대 보유일')
     , ('partial_exit_atr_mult', '3.0', '부분 익절 ATR 배수')
ON CONFLICT (key) DO NOTHING;
