class GdAssetError(Exception):
    pass

class BadRepoError(GdAssetError):
    def __init__(repo_type, path, details):
        self.repo_type = repo_type
        self.path = path
        self.details = details

    def __str__(self):
        return f"Invalid {self.repo_type} repository at {self.path}: {self.details}"
