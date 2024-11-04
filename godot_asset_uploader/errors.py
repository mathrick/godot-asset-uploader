class GdAssetError(Exception):
    pass

class HTTPRequestError(GdAssetError):
    pass

class NoImplementationError(GdAssetError):
    "Signalled when existing functionality lacks an implementation for a specific case"
    pass

class DependencyMissingError(GdAssetError):
    "Signalled when a dependency (such as Mercurial) is required but was not found"
    pass

class BadRepoError(GdAssetError):
    def __init__(repo_type, path, details):
        self.repo_type = repo_type
        self.path = path
        self.details = details

    def __str__(self):
        return f"Invalid {self.repo_type} repository at {self.path}: {self.details}"
