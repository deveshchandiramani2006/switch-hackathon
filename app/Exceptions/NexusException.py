class NexusException(Exception):
    pass


class TenantNotFoundError(NexusException):
    pass


class AgentConnectionError(NexusException):
    pass


class LLMProviderError(NexusException):
    pass


class ApprovalTimeoutError(NexusException):
    pass
