"""Banking Assistant Agent — core package.

Modular components:
    data_loader        Transaction retrieval (CSV -> validated DataFrame)
    query_parser        Natural-language query -> structured query (LLM + fallback)
    filters             Deterministic transaction filtering
    categorizer         Category validation / normalization / inference
    analytics           Deterministic financial calculations
    anomaly_detector    Statistical / rule-based anomaly detection
    summarizer          AI-assisted (or template) summary generation
    validators          Pydantic schemas shared across modules
"""
