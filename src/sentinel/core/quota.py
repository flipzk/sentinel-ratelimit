from dataclasses import dataclass
from enum import StrEnum

class UserTier(StrEnum):
    FREE = "free"
    PREMIUM = "premium"
    VIP = "vip"

@dataclass(frozen=True)
class Quota:
    limit: int
    window: int

class QuotaManager:
    """
    Decides the rate limit quotas based on user tiers or risk scores.
    In a real app, this would query a database or cache.
    """
    
    # Hardcoded configuration for demonstration
    TIER_CONFIG = {
        UserTier.FREE: Quota(limit=5, window=60),      # Very strict
        UserTier.PREMIUM: Quota(limit=50, window=60),  # Standard
        UserTier.VIP: Quota(limit=500, window=60),     # High throughput
    }

    def get_quota(self, api_key: str | None) -> Quota:
        """
        Determines the quota dynamically based on the API Key.
        """
        tier = self._resolve_tier(api_key)
        return self.TIER_CONFIG[tier]

    def _resolve_tier(self, api_key: str | None) -> UserTier:
        """
        Simulates looking up a user's tier in a database.
        """
        if not api_key:
            return UserTier.FREE
            
        # Simulating Database Lookup based on key prefix
        if api_key.startswith("vip_"):
            return UserTier.VIP
        elif api_key.startswith("prem_"):
            return UserTier.PREMIUM
            
        return UserTier.FREE