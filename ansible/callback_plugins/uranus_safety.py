"""Reject selective execution before Ansible can skip the input guard itself."""

from ansible.plugins.callback import CallbackBase

from ansible import context


class CallbackModule(CallbackBase):
    CALLBACK_VERSION = 2.0
    CALLBACK_TYPE = "aggregate"
    CALLBACK_NAME = "uranus_safety"
    CALLBACK_NEEDS_ENABLED = True

    def v2_playbook_on_start(self, playbook):
        if (
            set(context.CLIARGS.get("tags", ("all",))) != {"all"}
            or context.CLIARGS.get("skip_tags")
            or context.CLIARGS.get("start_at_task")
        ):
            # Ordinary callback Exceptions are only warnings in Ansible. Exit before tasks.
            raise SystemExit(
                "Do not bypass preflight or safety gates with tags, skip-tags or start-at-task."
            )
