import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class CommandDescriptions:
    start: str
    newevent: str
    endevent: str
    broadcast: str
    stats: str
    export: str
    history: str
    broadcasts: str
    visualize: str
    version: str
    dbexport: str


@dataclass
class RegistrationMessages:
    no_active_event: str
    event_not_available: str
    event_already_ended: str
    event_ended_notification: str
    question_intro: str
    unknown_message: str
    register_button: str
    skip_button: str


@dataclass
class BroadcastMessages:
    history_intro: str
    no_history: str
    history_header: str
    end_event_intro: str


@dataclass
class VisualizationMessages:
    generating: str
    success: str
    local_success: str
    no_events: str


@dataclass
class DbexportMessages:
    generating: str
    success: str
    success_url: str
    error: str


@dataclass
class EventDefaults:
    registration_success: str
    already_registered: str
    confirm_button: str
    confirm_message: str
    cancel_button: str
    cancel_message: str


@dataclass
class Config:
    commands: CommandDescriptions
    registration: RegistrationMessages
    broadcast: BroadcastMessages
    visualization: VisualizationMessages
    dbexport: DbexportMessages
    event_defaults: EventDefaults
    admin_ids: list[int] = field(default_factory=list)
    admin_group_id: int | None = None

    def is_admin(self, user_id: int) -> bool:
        return user_id in self.admin_ids

    def is_admin_context(self, chat_id: int, user_id: int) -> bool:
        """Check valid admin context (right chat + user is admin)."""
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

        bot = data["bot"]
        cmd = data["commands"]
        reg = data["registration"]
        bc = data["broadcast"]
        vis = data["visualization"]
        dbx = data["dbexport"]
        evt = data["event_defaults"]

        return cls(
            admin_ids=bot["admin_ids"],
            admin_group_id=bot.get("admin_group_id"),
            commands=CommandDescriptions(
                start=cmd["start"],
                newevent=cmd["newevent"],
                endevent=cmd["endevent"],
                broadcast=cmd["broadcast"],
                stats=cmd["stats"],
                export=cmd["export"],
                history=cmd["history"],
                broadcasts=cmd["broadcasts"],
                visualize=cmd["visualize"],
                version=cmd["version"],
                dbexport=cmd["dbexport"],
            ),
            registration=RegistrationMessages(
                no_active_event=reg["no_active_event"],
                event_not_available=reg["event_not_available"],
                event_already_ended=reg["event_already_ended"],
                event_ended_notification=reg["event_ended_notification"],
                question_intro=reg["question_intro"],
                unknown_message=reg["unknown_message"],
                register_button=reg["register_button"],
                skip_button=reg["skip_button"],
            ),
            broadcast=BroadcastMessages(
                history_intro=bc["history_intro"],
                no_history=bc["no_history"],
                history_header=bc["history_header"],
                end_event_intro=bc["end_event_intro"],
            ),
            visualization=VisualizationMessages(
                generating=vis["generating"],
                success=vis["success"],
                local_success=vis["local_success"],
                no_events=vis["no_events"],
            ),
            dbexport=DbexportMessages(
                generating=dbx["generating"],
                success=dbx["success"],
                success_url=dbx["success_url"],
                error=dbx["error"],
            ),
            event_defaults=EventDefaults(
                registration_success=evt["registration_success"],
                already_registered=evt["already_registered"],
                confirm_button=evt["confirm_button"],
                confirm_message=evt["confirm_message"],
                cancel_button=evt["cancel_button"],
                cancel_message=evt["cancel_message"],
            ),
        )
