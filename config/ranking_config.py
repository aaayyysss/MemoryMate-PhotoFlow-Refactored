"""
RankingConfig - Dynamic Configuration for Search Ranking Weights

Centralizes all ranking/scoring weight parameters so they can be
tuned from the Preferences dialog (Search & Discovery tab).

Each preset family (scenic, type, people_event, utility) has its own
weight profile.  The *default* family weights are user-tunable; the
per-family overrides remain fixed but reference the defaults as a
starting point when the user resets.

Usage:
    from config.ranking_config import RankingConfig

    # Get default (scenic) weights
    weights = RankingConfig.get_default_weights()

    # Get recency guardrails
    halflife = RankingConfig.get_recency_halflife_days()
"""

from dataclasses import dataclass

from logging_config import get_logger

logger = get_logger(__name__)


# ── Hardcoded best-practice defaults ──

@dataclass
class RankingDefaults:
    """Default ranking weight values (scenic / general profile)."""

    # Primary scoring weights (must sum to ~1.0)
    W_CLIP: float = 0.75
    W_RECENCY: float = 0.05
    W_FAVORITE: float = 0.08
    W_LOCATION: float = 0.04
    W_FACE_MATCH: float = 0.08
    W_STRUCTURAL: float = 0.00

    # Guardrails
    MAX_RECENCY_BOOST: float = 0.10
    MAX_FAVORITE_BOOST: float = 0.15
    RECENCY_HALFLIFE_DAYS: int = 90

    # Metadata soft-boost values (applied on top of semantic score)
    META_BOOST_GPS: float = 0.05
    META_BOOST_RATING: float = 0.10
    META_BOOST_DATE: float = 0.03

    # Dynamic threshold backoff
    THRESHOLD_BACKOFF_STEP: float = 0.04
    THRESHOLD_BACKOFF_MAX_RETRIES: int = 2


class RankingConfig:
    """
    Centralized ranking configuration.

    Reads from user preferences with fallback to RankingDefaults.
    """

    # ── Weight getters ──

    @classmethod
    def get_w_clip(cls) -> float:
        return cls._get_float("ranking_w_clip", RankingDefaults.W_CLIP, 0.0, 1.0)

    @classmethod
    def get_w_recency(cls) -> float:
        return cls._get_float("ranking_w_recency", RankingDefaults.W_RECENCY, 0.0, 1.0)

    @classmethod
    def get_w_favorite(cls) -> float:
        return cls._get_float("ranking_w_favorite", RankingDefaults.W_FAVORITE, 0.0, 1.0)

    @classmethod
    def get_w_location(cls) -> float:
        return cls._get_float("ranking_w_location", RankingDefaults.W_LOCATION, 0.0, 1.0)

    @classmethod
    def get_w_face_match(cls) -> float:
        return cls._get_float("ranking_w_face_match", RankingDefaults.W_FACE_MATCH, 0.0, 1.0)

    @classmethod
    def get_w_structural(cls) -> float:
        return cls._get_float("ranking_w_structural", RankingDefaults.W_STRUCTURAL, 0.0, 1.0)

    # ── Guardrail getters ──

    @classmethod
    def get_max_recency_boost(cls) -> float:
        return cls._get_float("ranking_max_recency_boost", RankingDefaults.MAX_RECENCY_BOOST, 0.0, 1.0)

    @classmethod
    def get_max_favorite_boost(cls) -> float:
        return cls._get_float("ranking_max_favorite_boost", RankingDefaults.MAX_FAVORITE_BOOST, 0.0, 1.0)

    @classmethod
    def get_recency_halflife_days(cls) -> int:
        return cls._get_int("ranking_recency_halflife_days", RankingDefaults.RECENCY_HALFLIFE_DAYS, 1, 730)

    # ── Metadata boost getters ──

    @classmethod
    def get_meta_boost_gps(cls) -> float:
        return cls._get_float("ranking_meta_boost_gps", RankingDefaults.META_BOOST_GPS, 0.0, 0.50)

    @classmethod
    def get_meta_boost_rating(cls) -> float:
        return cls._get_float("ranking_meta_boost_rating", RankingDefaults.META_BOOST_RATING, 0.0, 0.50)

    @classmethod
    def get_meta_boost_date(cls) -> float:
        return cls._get_float("ranking_meta_boost_date", RankingDefaults.META_BOOST_DATE, 0.0, 0.50)

    # ── Threshold backoff getters ──

    @classmethod
    def get_threshold_backoff_step(cls) -> float:
        return cls._get_float("ranking_backoff_step", RankingDefaults.THRESHOLD_BACKOFF_STEP, 0.01, 0.20)

    @classmethod
    def get_threshold_backoff_max_retries(cls) -> int:
        return cls._get_int("ranking_backoff_max_retries", RankingDefaults.THRESHOLD_BACKOFF_MAX_RETRIES, 0, 5)

    # ── Setters ──

    @classmethod
    def set_w_clip(cls, v: float) -> bool:
        return cls._set_float("ranking_w_clip", v, 0.0, 1.0)

    @classmethod
    def set_w_recency(cls, v: float) -> bool:
        return cls._set_float("ranking_w_recency", v, 0.0, 1.0)

    @classmethod
    def set_w_favorite(cls, v: float) -> bool:
        return cls._set_float("ranking_w_favorite", v, 0.0, 1.0)

    @classmethod
    def set_w_location(cls, v: float) -> bool:
        return cls._set_float("ranking_w_location", v, 0.0, 1.0)

    @classmethod
    def set_w_face_match(cls, v: float) -> bool:
        return cls._set_float("ranking_w_face_match", v, 0.0, 1.0)

    @classmethod
    def set_w_structural(cls, v: float) -> bool:
        return cls._set_float("ranking_w_structural", v, 0.0, 1.0)

    @classmethod
    def set_max_recency_boost(cls, v: float) -> bool:
        return cls._set_float("ranking_max_recency_boost", v, 0.0, 1.0)

    @classmethod
    def set_max_favorite_boost(cls, v: float) -> bool:
        return cls._set_float("ranking_max_favorite_boost", v, 0.0, 1.0)

    @classmethod
    def set_recency_halflife_days(cls, v: int) -> bool:
        return cls._set_int("ranking_recency_halflife_days", v, 1, 730)

    @classmethod
    def set_meta_boost_gps(cls, v: float) -> bool:
        return cls._set_float("ranking_meta_boost_gps", v, 0.0, 0.50)

    @classmethod
    def set_meta_boost_rating(cls, v: float) -> bool:
        return cls._set_float("ranking_meta_boost_rating", v, 0.0, 0.50)

    @classmethod
    def set_meta_boost_date(cls, v: float) -> bool:
        return cls._set_float("ranking_meta_boost_date", v, 0.0, 0.50)

    @classmethod
    def set_threshold_backoff_step(cls, v: float) -> bool:
        return cls._set_float("ranking_backoff_step", v, 0.01, 0.20)

    @classmethod
    def set_threshold_backoff_max_retries(cls, v: int) -> bool:
        return cls._set_int("ranking_backoff_max_retries", v, 0, 5)

    # ── Internal helpers ──

    @classmethod
    def _get_float(cls, key: str, default: float, lo: float, hi: float) -> float:
        try:
            from settings_manager_qt import SettingsManager
            settings = SettingsManager()
            value = settings.get(key, None)
            if value is not None:
                v = float(value)
                if lo <= v <= hi:
                    return v
                logger.warning(f"[RankingConfig] {key}={v} out of range [{lo},{hi}], using default")
        except Exception as e:
            logger.debug(f"[RankingConfig] Could not read {key}: {e}")
        return default

    @classmethod
    def _get_int(cls, key: str, default: int, lo: int, hi: int) -> int:
        try:
            from settings_manager_qt import SettingsManager
            settings = SettingsManager()
            value = settings.get(key, None)
            if value is not None:
                v = int(value)
                if lo <= v <= hi:
                    return v
                logger.warning(f"[RankingConfig] {key}={v} out of range [{lo},{hi}], using default")
        except Exception as e:
            logger.debug(f"[RankingConfig] Could not read {key}: {e}")
        return default

    @classmethod
    def _set_float(cls, key: str, v: float, lo: float, hi: float) -> bool:
        if not lo <= v <= hi:
            logger.warning(f"[RankingConfig] Invalid {key}={v}")
            return False
        try:
            from settings_manager_qt import SettingsManager
            settings = SettingsManager()
            settings.set(key, v)
            logger.info(f"[RankingConfig] Saved {key}={v}")
            return True
        except Exception as e:
            logger.error(f"[RankingConfig] Failed to save {key}: {e}")
            return False

    @classmethod
    def _set_int(cls, key: str, v: int, lo: int, hi: int) -> bool:
        if not lo <= v <= hi:
            logger.warning(f"[RankingConfig] Invalid {key}={v}")
            return False
        try:
            from settings_manager_qt import SettingsManager
            settings = SettingsManager()
            settings.set(key, v)
            logger.info(f"[RankingConfig] Saved {key}={v}")
            return True
        except Exception as e:
            logger.error(f"[RankingConfig] Failed to save {key}: {e}")
            return False
