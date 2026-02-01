"""
ECHO OS Barebone: Environment variable configuration

All service-specific values are now configurable via environment variables.
"""
import os


class Env:
    """Environment configuration for ECHO OS"""

    # ==========================================================================
    # Service Identity (Customizable)
    # ==========================================================================
    SERVICE_NAME = os.getenv("SERVICE_NAME", "AIアシスタント")
    OFFICE_NAME = os.getenv("OFFICE_NAME", "")
    PERSONA_NAME = os.getenv("PERSONA_NAME", "AIエキスパート")
    BASE_DOMAIN = os.getenv("BASE_DOMAIN", "example.com")
    DEFAULT_OFFICE_ID = os.getenv("DEFAULT_OFFICE_ID", "default")

    # ==========================================================================
    # RAG Layer Feature Flags
    # ==========================================================================
    L1_ENABLED = os.getenv("L1_ENABLED", "true").lower() == "true"
    L3_ENABLED = os.getenv("L3_ENABLED", "false").lower() == "true"
    L4_ENABLED = os.getenv("L4_ENABLED", "true").lower() == "true"
    L5_ENABLED = os.getenv("L5_ENABLED", "false").lower() == "true"

    # ==========================================================================
    # Layer 5 (Conversation Memory) Configuration
    # ==========================================================================
    L5_K_RECENT = int(os.getenv("L5_K_RECENT", "5"))
    L5_SEMANTIC_ENABLED = os.getenv("L5_SEMANTIC_ENABLED", "false").lower() == "true"
    L5_SEMANTIC_K = int(os.getenv("L5_SEMANTIC_K", "6"))
    L5_SEMANTIC_REBUILD_THRESHOLD = int(os.getenv("L5_SEMANTIC_REBUILD_THRESHOLD", "50"))
    L5_SEMANTIC_MAX_ITEMS = int(os.getenv("L5_SEMANTIC_MAX_ITEMS", "5000"))
    L5_S3_BUCKET = os.getenv("L5_S3_BUCKET", "")
    L5_S3_LIFECYCLE_DAYS = int(os.getenv("L5_S3_LIFECYCLE_DAYS", "180"))

    # ==========================================================================
    # AWS Configuration
    # ==========================================================================
    AWS_REGION = os.getenv("AWS_REGION", "ap-northeast-1")

    # DynamoDB Tables
    DDB_TABLE_CONV = os.getenv("DDB_TABLE_CONV", "ConversationMemory")
    DDB_TABLE_THREADS = os.getenv("DDB_TABLE_THREADS", "ConversationThreads")
    DDB_TABLE_MESSAGES = os.getenv("DDB_TABLE_MESSAGES", "ConversationMessages")
    DDB_TABLE_TENANTS = os.getenv("DDB_TABLE_TENANTS", "Tenants")
    DDB_TABLE_CLIENTS = os.getenv("DDB_TABLE_CLIENTS", "Clients")
    DDB_TABLE_CLIENT_TOKENS = os.getenv("DDB_TABLE_CLIENT_TOKENS", "ClientTokens")
    DDB_TABLE_ESCALATION = os.getenv("DDB_TABLE_ESCALATION", "EscalationQueue")
    DDB_TABLE_FEATURE_FLAGS = os.getenv("DDB_TABLE_FEATURE_FLAGS", "FeatureFlags")
    DDB_TABLE_SESSIONS = os.getenv("DDB_TABLE_SESSIONS", "Sessions")
    DDB_TABLE_GFS_SYNC = os.getenv("DDB_TABLE_GFS_SYNC", "GFSSyncState")
    DDB_TABLE_L4_CHUNKS = os.getenv("DDB_TABLE_L4_CHUNKS", "L4Chunks")
    DDB_TABLE_SYNC_JOBS = os.getenv("DDB_TABLE_SYNC_JOBS", "SyncJobs")
    DDB_TABLE_CBR_CASES = os.getenv("DDB_TABLE_CBR_CASES", "CBRCases")

    # ==========================================================================
    # API Keys
    # ==========================================================================
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")

    # ==========================================================================
    # Feature Flags
    # ==========================================================================
    SHARED_HISTORY_ENABLED = os.getenv("SHARED_HISTORY_ENABLED", "true").lower() == "true"
    CLIENT_PORTAL_ENABLED = os.getenv("CLIENT_PORTAL_ENABLED", "false").lower() == "true"
    CLIENT_AUTH_BYPASS = os.getenv("CLIENT_AUTH_BYPASS", "false").lower() == "true"
    LEGACY_COMPAT_ENABLED = os.getenv("LEGACY_COMPAT_ENABLED", "false").lower() == "true"
    CBR_ENABLED = os.getenv("CBR_ENABLED", "false").lower() == "true"

    # ==========================================================================
    # Microsoft OAuth
    # ==========================================================================
    MICROSOFT_OAUTH_CLIENT_ID = os.getenv("MICROSOFT_OAUTH_CLIENT_ID", "")
    MICROSOFT_OAUTH_CLIENT_SECRET = os.getenv("MICROSOFT_OAUTH_CLIENT_SECRET", "")
    MICROSOFT_OAUTH_REDIRECT_URI = os.getenv("MICROSOFT_OAUTH_REDIRECT_URI", "")
    MICROSOFT_OAUTH_TENANT_ID = os.getenv("MICROSOFT_OAUTH_TENANT_ID", "common")
    MICROSOFT_OAUTH_REFRESH_TOKEN = os.getenv("MICROSOFT_OAUTH_REFRESH_TOKEN", "")

    # OneDrive Poller
    ONEDRIVE_POLLER_ENABLED = os.getenv("ONEDRIVE_POLLER_ENABLED", "false").lower() == "true"
    ONEDRIVE_POLL_INTERVAL_MINUTES = int(os.getenv("ONEDRIVE_POLL_INTERVAL_MINUTES", "60"))

    # ==========================================================================
    # JWT Configuration
    # ==========================================================================
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")
    JWT_KEY_ID = os.getenv("JWT_KEY_ID", "v1")
    JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
    JWT_LEEWAY = int(os.getenv("JWT_LEEWAY", "30"))

    # Session Configuration
    SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", "client_session")
    SESSION_MAX_AGE = int(os.getenv("SESSION_MAX_AGE", str(30*24*3600)))
    CSRF_COOKIE_NAME = os.getenv("CSRF_COOKIE_NAME", "csrf_token")

    # ==========================================================================
    # Google Drive (GFS) Integration
    # ==========================================================================
    GFS_ENABLED = os.getenv("GFS_ENABLED", "false").lower() == "true"
    GFS_ROOT_FOLDER_ID = os.getenv("GFS_ROOT_FOLDER_ID", "")
    GFS_SERVICE_ACCOUNT_JSON = os.getenv("GFS_SERVICE_ACCOUNT_JSON", "")
    GFS_POLL_INTERVAL_MINUTES = int(os.getenv("GFS_POLL_INTERVAL_MINUTES", "60"))

    # ==========================================================================
    # L4 RAG Configuration
    # ==========================================================================
    L4_USE_GEMINI_FILE_SEARCH = os.getenv("L4_USE_GEMINI_FILE_SEARCH", "false").lower() == "true"
    L4_USE_AZURE_AI_SEARCH = os.getenv("L4_USE_AZURE_AI_SEARCH", "false").lower() == "true"

    # ==========================================================================
    # Azure AI Search Configuration
    # ==========================================================================
    AZURE_SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT", "")
    AZURE_SEARCH_API_KEY = os.getenv("AZURE_SEARCH_API_KEY", "")
    AZURE_SEARCH_INDEX_NAME = os.getenv("AZURE_SEARCH_INDEX_NAME", "knowledge")
    L1_USE_AZURE_AI_SEARCH = os.getenv("L1_USE_AZURE_AI_SEARCH", "false").lower() == "true"
    AZURE_SEARCH_L1_INDEX_NAME = os.getenv("AZURE_SEARCH_L1_INDEX_NAME", "l1-legal-hybrid")


# Singleton instance
env = Env()
