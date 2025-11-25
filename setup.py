from setuptools import setup, find_packages

setup(
    name="ontplan",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        # LangGraph & LangChain
        "langgraph>=1.0.3",
        "langchain>=1.0.7",
        "langchain-core>=1.0.5",
        "langchain-openai>=1.0.3",
        "langgraph-checkpoint>=3.0.0",
        "langgraph-sdk>=0.2.0",

        # Ontology & Knowledge Graph
        "owlready2>=0.48",
        "neo4j>=6.0.0",
        "rdflib>=7.0.0",

        # API & Web
        "fastapi>=0.121.0",
        "uvicorn>=0.38.0",
        "pydantic>=2.12.0",

        # OpenAI
        "openai>=2.8.0",
        "tiktoken>=0.12.0",

        # Utilities
        "python-dotenv>=1.2.0",
        "PyYAML>=6.0.0",
        "numpy>=2.3.0",
        "requests>=2.32.0",
    ],
    python_requires=">=3.11",
    description="Ontology-based robot task planning system with LangGraph",
    author="OntoPlan Team",
    license="MIT",
)
