from enum import Enum

class UserRole(str, Enum):
    USER = "user"
    ADMIN = "admin"

class NotificationPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

class ArticleCategory(str, Enum):
    PRESIDENT = "president"
    PARLIAMENT = "parliament"
    POLITICS = "politics"
    BREAKING = "breaking"
    GOVERNMENT = "government"