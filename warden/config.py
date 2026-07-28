"""
Warden global configuration.

Centralizes all settings: model paths, thresholds, tier configs, and
feature flags. Loaded once at startup, referenced everywhere.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class TrustLevel(Enum):
    """Trust classification for incoming content."""
    TRUSTED = "trusted"         # User's direct input, system prompts
    UNTRUSTED = "untrusted"     # Fetched web content, tool outputs, external files
    AMBIGUOUS = "ambiguous"     # Source unclear — treat as untrusted


class ContentSource(Enum):
    """Origin of content entering the system."""
    USER_DIRECT = "user_direct"
    FETCHED_URL = "fetched_url"
    TOOL_OUTPUT = "tool_output"
    LOCAL_FILE = "local_file"
    CODE_DIFF = "code_diff"
    UNKNOWN = "unknown"


class Decision(Enum):
    """Security decision outcome."""
    ALLOW = "allow"
    BLOCK = "block"
    FLAG = "flag"           # Allow but warn the user
    UNCERTAIN = "uncertain" # Needs escalation to next tier
    EXTRACT_ONLY = "extract_only" # Safe but untrusted — route to Q-LLM


class OperatingMode(Enum):
    """Warden operating modes."""
    ACTIVE = "active"       # Blocks threats, allows clean content
    SHADOW = "shadow"       # Logs everything, blocks nothing
    REPORT = "report"       # Offline analysis of historical data


@dataclass
class RoutingConfig:
    """Configuration for the Intelligent Routing Engine."""

    # Escalation thresholds
    tier0_to_tier1: float = 0.3     # Tier 0 suspicion score → escalate
    tier1_to_tier2: float = 0.4     # Tier 1 confidence below this → escalate
    auto_block: float = 0.85        # Tier 1 confidence above this → block without GPU
    auto_allow: float = 0.05        # Tier 1 confidence below this → allow without GPU

    # Batch scheduler
    batch_window_ms: int = 100
    max_batch_size: int = 8

    # Timeouts
    tier2_timeout_s: float = 30.0   # Max seconds for a Tier 2 GPU call
    rag_timeout_s: float = 5.0      # Max seconds for RAG retrieval


@dataclass
class ModelConfig:
    """Configuration for LLM models."""

    # Tier 2 / P-LLM / Q-LLM model (same model, different roles)
    llm_model_path: str = ""
    llm_n_gpu_layers: int = -1      # -1 = offload all layers to GPU
    llm_n_ctx: int = 4096           # Context window
    llm_temperature: float = 0.1    # Low temp for deterministic classification

    # ROCm optimization parameters
    llm_flash_attn: bool = True     # Flash attention acceleration on Radeon GPUs
    llm_offload_kqv: bool = True    # Offload KQV directly into Radeon VRAM
    llm_n_batch: int = 512          # Prompt batch size for wide parallel instruction processing

    # AMD TokenFactory API Integration (Optional Cloud Endpoint Mode)
    tokenfactory_endpoint: str = ""
    tokenfactory_api_key: str = ""
    tokenfactory_model: str = "qwen2.5-coder-7b-instruct"

    # Tier 1 ML Classifier
    classifier_model_name: str = "protectai/deberta-v3-base-prompt-injection-v2"
    classifier_threshold_block: float = 0.85
    classifier_device: str = "cpu"  # Prompt Guard 2 always on CPU

    # Model selection note: default is Qwen2.5-Coder-7B-Instruct (Q4_K_M)
    # Change llm_model_path based on what GPU is provided on AMD Radeon Cloud


@dataclass
class WardenConfig:
    """Top-level Warden configuration."""

    # Operating mode
    mode: OperatingMode = OperatingMode.ACTIVE

    # Sub-configs
    routing: RoutingConfig = field(default_factory=RoutingConfig)
    model: ModelConfig = field(default_factory=ModelConfig)

    # Paths
    policy_path: str = "policies/default.yaml"
    audit_db_path: str = "warden_audit.db"
    rag_db_path: str = "warden_rag_db"
    attack_samples_path: str = "attack_samples"

    # Feature flags
    enable_camel: bool = True       # Use CaMeL dual-LLM split
    enable_rag: bool = True         # Use RAG augmentation for Tier 2
    enable_memory: bool = True      # Use pattern memory shortcuts
    enable_batch: bool = True       # Use batch scheduler for GPU calls

    @classmethod
    def from_env(cls) -> "WardenConfig":
        """Load configuration from environment variables."""
        config = cls()
        if model_path := os.environ.get("WARDEN_MODEL_PATH"):
            config.model.llm_model_path = model_path
        if endpoint := os.environ.get("WARDEN_TOKENFACTORY_ENDPOINT"):
            config.model.tokenfactory_endpoint = endpoint
        if api_key := os.environ.get("WARDEN_TOKENFACTORY_API_KEY"):
            config.model.tokenfactory_api_key = api_key
        if policy := os.environ.get("WARDEN_POLICY"):
            config.policy_path = policy
        if mode := os.environ.get("WARDEN_MODE"):
            config.mode = OperatingMode(mode)
        if auto_block := os.environ.get("WARDEN_AUTO_BLOCK"):
            config.routing.auto_block = float(auto_block)
        if tier2_timeout := os.environ.get("WARDEN_TIER2_TIMEOUT"):
            config.routing.tier2_timeout_s = float(tier2_timeout)
        return config
