# GEMINI.md

## Project Overview

This project is a Python-based agent that integrates OpenAI's Deep Research API with Claude Code through the Model Context Protocol (MCP). It allows users to perform comprehensive, autonomous research tasks with web search, code execution, and citation management capabilities directly within the Claude Code environment.

The project is structured as a standard Python application with three main components:

*   **`src/deep_research_mcp/config.py`**: Manages configuration, loading settings from environment variables and a `.env` file.
*   **`src/deep_research_mcp/agent.py`**: Contains the core logic for interacting with the OpenAI Deep Research API, including creating research tasks, polling for completion, and handling errors.
*   **`src/deep_research_mcp/mcp_server.py`**: Implements the MCP server using the `fastmcp` library, exposing the research functionality as tools to be used within Claude Code.

The agent supports asynchronous operations, rate limiting, and configurable settings for the research model, timeout, and other parameters.

## Building and Running

### Prerequisites

*   Python 3.9+
*   An OpenAI API key with access to Deep Research models.

### Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/pminervini/deep-research-mcp.git
    cd deep-research-mcp
    ```

2.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Set up environment variables:**
    Create a `.env` file in the project root by copying the example:
    ```bash
    cp .env.example .env
    ```
    Then, edit the `.env` file to add your `OPENAI_API_KEY`.

### Running the MCP Server

To make the research tools available to Claude Code, run the MCP server:

```bash
python src/deep_research_mcp/mcp_server.py
```

The server will start and listen for requests from Claude Code. You will need to configure Claude Code to connect to this server as described in the `README.md`.

### Running as a Standalone Module

You can also use the `DeepResearchAgent` directly in your own Python scripts:

```python
import asyncio
from deep_research_mcp.agent import DeepResearchAgent
from deep_research_mcp.config import ResearchConfig

async def main():
    # Initialize configuration
    config = ResearchConfig.from_env()
    
    # Create agent
    agent = DeepResearchAgent(config)
    
    # Perform research
    result = await agent.research(
        query="What are the latest advances in quantum computing?",
        system_prompt="Focus on practical applications and recent breakthroughs"
    )
    
    # Print results
    print(f"Report: {result['final_report']}")
    print(f"Citations: {result['citations']}")
    print(f"Research steps: {result['total_steps']}")

# Run the research
asyncio.run(main())
```

## Development Conventions

### Testing

The project uses `pytest` for testing. To run the tests:

```bash
pytest
```

To run tests with coverage:

```bash
pytest --cov=deep_research_mcp tests/
```

### Code Style

The code follows standard Python conventions (PEP 8). While no specific linter is enforced in the `requirements.txt`, it is recommended to use a tool like `flake8` or `black` to maintain a consistent code style.

**Important**: Never use emojis in code, comments, docstrings, or any part of the codebase.

### Contribution Guidelines

The `README.md` does not specify any contribution guidelines. However, based on the project structure, it is recommended to:

*   Add new functionality to the `agent.py` file.
*   Expose new functionality as tools in the `mcp_server.py` file.
*   Add or update configuration settings in the `config.py` file.
*   Add tests for any new functionality in the `tests/` directory.
