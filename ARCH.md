# Architecture

This document provides a detailed overview of the `deep-research-mcp` project architecture, including component interactions and file-by-file descriptions.

## Architectural Diagram (Mermaid)

```mermaid
graph TD
    subgraph User/Client
        A[Claude Code]
    end

    subgraph MCP Server
        B[mcp_server.py]
        C[FastMCP]
    end

    subgraph Core Logic
        D[agent.py]
        E[config.py]
        F[errors.py]
        G[clarification.py]
    end

    subgraph Clarification System
        G1[TriageAgent]
        G2[ClarifierAgent]
        G3[ClarificationManager]
        G4[ClarificationSession]
    end

    subgraph External Services
        H[OpenAI Deep Research API]
        I[OpenAI Chat API for Clarification]
    end

    A -- "Makes tool calls (deep_research, research_with_context)" --> B
    B -- "Uses" --> C
    B -- "Instantiates and uses" --> D
    D -- "Uses configuration from" --> E
    D -- "Handles" --> F
    D -- "Uses clarification from" --> G
    D -- "Makes API calls to" --> H
    
    G --> G1
    G --> G2
    G --> G3
    G3 --> G4
    G1 -- "Analyzes queries" --> I
    G2 -- "Enriches queries" --> I
```

## Component Descriptions

The project is composed of four main layers:

1.  **MCP Server (`mcp_server.py`)**: This is the entry point for external clients like Claude Code. It uses the `fastmcp` library to expose the core research functionality as tools. It handles incoming requests, initializes the `DeepResearchAgent`, and formats the results for the client. Now includes three tools: `deep_research()`, `research_with_context()`, and `research_status()`.

2.  **Core Logic (`agent.py`, `config.py`, `errors.py`)**: This layer contains the main business logic of the application.
    *   `agent.py` is the heart of the project, managing the interaction with the OpenAI Deep Research API and coordinating clarification workflows.
    *   `config.py` handles loading and validating configuration from environment variables, including clarification settings.
    *   `errors.py` defines custom exception classes for better error handling.

3.  **Clarification System (`clarification.py`)**: This layer handles the optional clarification workflow to improve research quality through follow-up questions.
    *   `TriageAgent` analyzes queries to determine if clarification would be beneficial.
    *   `ClarifierAgent` enriches queries based on user responses to clarifying questions.
    *   `ClarificationManager` orchestrates the complete clarification workflow.
    *   `ClarificationSession` manages state for individual clarification sessions.

4.  **External Services**: This layer represents the external APIs the project interacts with, including the OpenAI Deep Research API and OpenAI Chat API (for clarification agents).

## File-by-File Breakdown

### `src/deep_research_mcp/agent.py`

-   **Purpose**: Contains the `DeepResearchAgent` class, which is the core component responsible for interacting with the OpenAI Deep Research API.
-   **Key Functionality**:
    -   `research()`: The main method that orchestrates the research process. It prepares the input, creates a research task, polls for completion, and formats the results.
    -   `_create_research_task()`: Sends the initial request to the OpenAI API to start a research task. It includes retry logic using the `tenacity` library.
    -   `_wait_for_completion()`: Polls the API for the status of a research task until it is completed, fails, or times out.
    -   `_send_completion_callback()`: Sends a notification to a callback URL when the research is complete.
    -   `_extract_results()`: Parses the final response from the API and extracts the report, citations, and other metadata.
    -   `get_task_status()`: Allows checking the status of a running research task.
    -   `start_clarification()`: Initiates the clarification process using the ClarificationManager.
    -   `add_clarification_answers()`: Adds user answers to clarification questions.
    -   `get_enriched_query()`: Retrieves an enriched query based on clarification responses.

### `src/deep_research_mcp/mcp_server.py`

-   **Purpose**: Implements the MCP (Model-Client Protocol) server using the `fastmcp` library. This file exposes the research functionality as tools that can be called by clients like Claude Code.
-   **Key Functionality**:
    -   `@mcp.tool() deep_research()`: The main tool that performs research. It initializes the `DeepResearchAgent`, calls its `research()` method, and formats the output for the client. Now supports clarification via the `request_clarification` parameter.
    -   `@mcp.tool() research_with_context()`: A new tool that performs research using enriched queries from clarification sessions. Takes a session ID and answers to clarifying questions.
    -   `@mcp.tool() research_status()`: A tool to check the status of a research task.
    -   `main()`: The entry point for running the MCP server. It loads the configuration and starts the server.

### `src/deep_research_mcp/config.py`

-   **Purpose**: Manages the application's configuration.
-   **Key Functionality**:
    -   `ResearchConfig` (dataclass): Defines the configuration parameters for the agent, such as API key, model name, timeout, poll interval, and clarification settings.
    -   `from_env()`: A class method to load configuration from environment variables. Configuration is loaded from a `~/.deep_research` TOML file that sets environment variables. This allows for easy configuration without hardcoding values. Now includes clarification settings.
    -   `validate()`: A method to validate the configuration to ensure that the provided values are valid.

### `src/deep_research_mcp/errors.py`

-   **Purpose**: Defines custom exception classes for the application.
-   **Key Functionality**:
    -   `ResearchError`: A base exception class for all research-related errors.
    -   `TaskTimeoutError`: An exception for when a research task takes too long to complete.
    -   `ConfigurationError`: An exception for errors in the application's configuration.


### `src/deep_research_mcp/clarification.py`

-   **Purpose**: Implements the clarification system for improving research quality through follow-up questions.
-   **Key Functionality**:
    -   `TriageAgent`: Analyzes research queries to determine if clarification would improve results. Uses configurable model for query analysis.
    -   `ClarifierAgent`: Takes user responses to questions and enriches the original query with additional context and specificity.
    -   `ClarificationSession`: Manages state for individual clarification sessions, including questions, answers, and session metadata.
    -   `ClarificationManager`: Orchestrates the complete workflow from triage through query enrichment, managing sessions and coordinating between agents.

### `src/deep_research_mcp/__init__.py`

-   **Purpose**: Initializes the `deep_research_mcp` package.
-   **Key Functionality**:
    -   Defines the package version (`__version__`).
    -   Exports the main classes and exceptions for easy importing.
