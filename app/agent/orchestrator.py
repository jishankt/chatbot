from app.agent.pipeline import CX02Pipeline

class CX02Orchestrator:
    def __init__(self, *args, **kwargs):
        self.pipeline = CX02Pipeline()

    def process_message(self, user_message: str, phone: str = "Unknown", conversation_history=None):
        return self.pipeline.process(user_message=user_message, phone=phone)
