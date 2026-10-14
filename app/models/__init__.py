from app.models.base import Base
from app.models.club import Club, ClubAdmin, Member, SystemConfig, SystemConfigHistory
from app.models.match import MatchEvent, MatchGame, MatchMember
from app.models.rating import PlayerRating, PlayerRatingHistory
from app.models.session import (
    ClubSession,
    SessionGuest,
    SessionMember,
    SessionTeam,
    SessionTeamMember,
    TeamAssignmentLog,
    TeamGeneration,
)
from app.models.stats import MemberPairStat, MemberStatSummary
from app.models.title import MemberTitle, TitleType
from app.models.wire import (
    AiArticle,
    AiArticleInsight,
    ArticleTag,
    Insight,
    InsightConfigParam,
    InsightMember,
    InsightTypeConfig,
)

from app.models.comments import apply_comments

apply_comments(Base.metadata)

__all__ = [
    "Base",
    "Club", "ClubAdmin", "Member", "SystemConfig", "SystemConfigHistory",
    "ClubSession", "SessionMember", "SessionGuest", "SessionTeam", "SessionTeamMember",
    "TeamGeneration", "TeamAssignmentLog",
    "MatchGame", "MatchMember", "MatchEvent",
    "PlayerRating", "PlayerRatingHistory",
    "MemberStatSummary", "MemberPairStat",
    "TitleType", "MemberTitle",
    "InsightTypeConfig", "InsightConfigParam", "Insight", "InsightMember",
    "AiArticle", "AiArticleInsight", "ArticleTag",
]
