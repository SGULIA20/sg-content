-- The clock claims a job by matching last_fired exactly, but the edge function reads it as a JS Date
-- (milliseconds), so a microsecond value never matched again and every job fired once only.
-- Millisecond precision on the column makes the round-trip exact.
alter table command.clock alter column last_fired type timestamptz(3);
