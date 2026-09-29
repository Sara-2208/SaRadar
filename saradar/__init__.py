"""SaRadar - AI job radar package.

Modules:
    config: Configuration loading from YAML and environment variables.
    llm: LLM abstraction layer supporting multiple providers.
    resume_parser: Resume file parsing (PDF, etc.).
    requirements_extractor: Extract structured requirements from job descriptions.
    scorer: Candidate-job fit scoring engine.
    jobs: Job sourcing from official APIs and email alerts.
    tailor: Resume tailoring logic.
    notify: Notification delivery (Telegram, etc.).
    db: SQLite database operations.
"""

__version__ = "0.1.0"
