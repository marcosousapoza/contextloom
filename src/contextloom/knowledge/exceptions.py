class KnowledgeError(Exception):
    """A controlled, user-facing knowledge operation failure."""


class ImportValidationError(KnowledgeError):
    def __init__(self, errors):
        self.errors = errors if isinstance(errors, list) else [str(errors)]
        super().__init__("; ".join(self.errors))
