from aiogram.fsm.state import State, StatesGroup


class NewEventStates(StatesGroup):
    title = State()
    description = State()
    datetime_text = State()
    event_code = State()
    custom_question = State()
    question_type = State()
    question_options = State()


class BroadcastStates(StatesGroup):
    message = State()
    confirm = State()


class RegistrationStates(StatesGroup):
    answer = State()


class HistoryBroadcastStates(StatesGroup):
    message = State()
    confirm = State()


class EndBroadcastStates(StatesGroup):
    message = State()
    confirm = State()
