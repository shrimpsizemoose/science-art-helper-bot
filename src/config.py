import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SystemMessages:
    no_active_event: str
    event_not_available: str
    register_button_text: str
    question_intro: str
    skip_question_button_text: str
    unknown_message: str
    start_command_description: str


@dataclass
class DefaultEventMessages:
    registration_success: str
    already_registered: str
    confirm_button_text: str
    confirm_confirmation: str
    cancel_button_text: str
    cancel_confirmation: str


@dataclass
class Config:
    admin_ids: list[int] = field(default_factory=list)
    admin_group_id: int | None = None
    system_messages: SystemMessages | None = None
    default_event_messages: DefaultEventMessages | None = None

    def is_admin(self, user_id: int) -> bool:
        return user_id in self.admin_ids

    def is_admin_context(self, chat_id: int, user_id: int) -> bool:
        """Check valid admin context (right chat + user is admin)."""  # noqa: DOC201
        if not self.is_admin(user_id):
            return False
        # If admin_group_id is set, only that group works
        # If not set, only DM works
        if self.admin_group_id:
            return chat_id == self.admin_group_id
        return chat_id == user_id  # DM

    @classmethod
    def load(cls, path: Path) -> "Config":
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        with path.open("rb") as f:
            data = tomllib.load(f)

        bot_data = data["bot"]
        sys_msg_data = data["system_messages"]
        event_msg_data = data["default_event_messages"]

        return cls(
            admin_ids=bot_data["admin_ids"],
            admin_group_id=bot_data.get("admin_group_id"),  # Optional
            system_messages=SystemMessages(
                no_active_event=sys_msg_data["no_active_event"],
                event_not_available=sys_msg_data["event_not_available"],
                register_button_text=sys_msg_data["register_button_text"],
                question_intro=sys_msg_data["question_intro"],
                skip_question_button_text=sys_msg_data["skip_question_button_text"],
                unknown_message=sys_msg_data["unknown_message"],
                start_command_description=sys_msg_data["start_command_description"],
            ),
            default_event_messages=DefaultEventMessages(
                registration_success=event_msg_data["registration_success"],
                already_registered=event_msg_data["already_registered"],
                confirm_button_text=event_msg_data["confirm_button_text"],
                confirm_confirmation=event_msg_data["confirm_confirmation"],
                cancel_button_text=event_msg_data["cancel_button_text"],
                cancel_confirmation=event_msg_data["cancel_confirmation"],
            ),
        )
