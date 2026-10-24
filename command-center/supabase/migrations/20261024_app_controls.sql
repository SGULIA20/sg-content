-- One menu for everything (24 Oct 2026): the control room's buttons also start the app posts (arthvan-media daily-post) and the
-- founder's LinkedIn post, so the second bot is not needed for controls.
alter table command.commands drop constraint commands_action_check;
alter table command.commands add constraint commands_action_check
  check (action in ('pause', 'resume', 'stop', 'retry', 'run_produce', 'run_publish', 'smb_ceo_report', 'app_post', 'app_linkedin'));
alter table command.commands drop constraint commands_target_check;
alter table command.commands add constraint commands_target_check check (target in ('sg-content', 'scoremybiz', 'arthvan-media'));
