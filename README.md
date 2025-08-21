# Deep Research MCP

A Python-based agent that integrates OpenAI's Deep Research API with Claude Code through the Model Context Protocol (MCP). This enables Claude Code to perform comprehensive, autonomous research tasks with web search, code execution, and citation management capabilities.

## Prerequisites

- Python 3.9+
- OpenAI API key with access to Deep Research models
- Claude Code, or any other assistant supporting MCP integration

## Configuration

### Configuration File

Create a `~/.deep_research` file in your home directory using TOML format:

```toml
[research]
# Core settings
research_model = "o4-mini-deep-research-2025-06-26"  # Research model to use
api_key = "sk-your-api-key-here"                     # Will use your OPENAI_API_KEY environment variable if not set
base_url = "https://api.openai.com/v1"               # Optional - Custom OpenAI-compatible endpoint for the research model

# Deep Research API settings
timeout = 1800      # Request timeout in seconds (30 minutes)
poll_interval = 30  # Polling interval for status checks in seconds
max_retries = 3     # Maximum number of retry attempts for failed requests

[clarification]
enable_clarification = true                           # Enable/disable the clarification pipeline
clarification_api_key = "sk-your-clarification-api-key-here"  # Optional custom API key for clarification agents
clarification_base_url = "https://api.openai.com/v1"  # Optional custom OpenAI-compatible endpoint for clarification agents
triage_model = "gpt-5-mini"                           # Model used for analyzing if queries need clarification
clarifier_model = "gpt-5-mini"                        # Model used for enriching queries with user responses
instruction_builder_model = "gpt-5-mini"              # Model used for building detailed research instructions

[logging]
level = "INFO"
```

### Claude Code Integration

1. **Configure MCP Server**

Add the MCP server using Claude Code's command line:

```bash
claude mcp add deep-research python /path/to/deep-research-mcp/src/deep_research_mcp/mcp_server.py
```

Replace `/path/to/deep-research-mcp/` with the actual path to your cloned repository.

2. **Use in Claude Code**:
   - The research tools will appear in Claude Code's tool palette
   - Simply ask Claude to "research [your topic]" and it will use the Deep Research agent
   - For clarified research, ask Claude to "research [topic] with clarification" to get follow-up questions

### OpenAI Codex Integration

1. **Configure MCP Server**

Add the MCP server configuration to your `~/.codex/config.toml` file:

```toml
[mcp_servers.deep-research]
command = "python"
args = ["/path/to/deep-research-mcp/src/deep_research_mcp/mcp_server.py"]
env = { "OPENAI_API_KEY" = "$OPENAI_API_KEY" }
```

Replace `/path/to/deep-research-mcp/` with the actual path to your cloned repository.

2. **Use in OpenAI Codex**:
   - The research tools will be available automatically when you start Codex
   - Ask Codex to "research [your topic]" and it will use the Deep Research MCP server
   - For clarified research, ask for "research [topic] with clarification"

### Gemini CLI Integration

1. **Configure MCP Server**

Add the MCP server using Gemini CLI's built-in command:

```bash
gemini mcp add deep-research python /path/to/deep-research-mcp/src/deep_research_mcp/mcp_server.py
```

Or manually add to your `~/.gemini/settings.json` file:

```json
{
  "mcpServers": {
    "deep-research": {
      "command": "python",
      "args": ["/path/to/deep-research-mcp/src/deep_research_mcp/mcp_server.py"],
      "env": {
        "OPENAI_API_KEY": "$OPENAI_API_KEY"
      }
    }
  }
}
```

Replace `/path/to/deep-research-mcp/` with the actual path to your cloned repository.

2. **Use in Gemini CLI**:
   - Start Gemini CLI with `gemini`
   - The research tools will be available automatically
   - Ask Gemini to "research [your topic]" and it will use the Deep Research MCP server
   - Use `/mcp` command to view server status and available tools

## Usage

### As a Standalone Python Module

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

### As an MCP Server

```bash
# Start the MCP server
python src/deep_research_mcp/mcp_server.py

# The server will now be available to Claude Code
```

### Example Queries

```python
# Basic research query
result = await agent.research("Explain the transformer architecture in AI")

# Research with code analysis
result = await agent.research(
    query="Analyze global temperature trends over the last 50 years",
    include_code_interpreter=True
)

# Custom system instructions
result = await agent.research(
    query="Review the safety considerations for AGI development",
    system_prompt="""
    Provide a balanced analysis including:
    - Technical challenges
    - Current safety research
    - Regulatory approaches
    - Industry perspectives
    Include specific examples and data where available.
    """
)

# With clarification (requires ENABLE_CLARIFICATION=true)
clarification_result = agent.start_clarification("quantum computing applications")
if clarification_result.get("needs_clarification"):
    # Answer questions programmatically or present to user
    answers = ["Hardware applications", "Last 5 years", "Commercial products"]
    agent.add_clarification_answers(clarification_result["session_id"], answers)
    enriched_query = agent.get_enriched_query(clarification_result["session_id"])
    result = await agent.research(enriched_query)
```

## Clarification Features

The agent includes an optional clarification system to improve research quality through follow-up questions.

### Configuration

Enable clarification in your `~/.deep_research` file:
```toml
enable_clarification = true
triage_model = "gpt-5-mini"      # Optional, defaults to gpt-5-mini
clarifier_model = "gpt-5-mini"   # Optional, defaults to gpt-5-mini
clarification_api_key = "sk-your-clarification-api-key-here"  # Optional custom API key for clarification models
clarification_base_url = "https://custom-api.example.com/v1"  # Optional custom endpoint for clarification models
```

### Usage Flow

1. **Start Clarification**:
   ```python
   result = agent.start_clarification("your research query")
   ```

2. **Check if Questions are Needed**:
   ```python
   if result.get("needs_clarification"):
       questions = result["questions"]
       session_id = result["session_id"]
   ```

3. **Provide Answers**:
   ```python
   answers = ["answer1", "answer2", "answer3"]
   agent.add_clarification_answers(session_id, answers)
   ```

4. **Get Enriched Query**:
   ```python
   enriched_query = agent.get_enriched_query(session_id)
   final_result = await agent.research(enriched_query)
   ```

### Integration with AI Asssitants

When using with AI Assistants via MCP tools:

1. **Request Clarification**: Use `deep_research()` with `request_clarification=True`
2. **Answer Questions**: The AI Assistant will present questions to you
3. **Deep Research**: The AI Asssitant will automatically use `research_with_context()` with your answers

## API Reference

### DeepResearchAgent

The main class for performing research operations.

#### Methods

- `research(query, system_prompt=None, include_code_interpreter=True, callback_url=None)`
  - Performs deep research on a query
  - Returns: Dictionary with final report, citations, and metadata

- `get_task_status(task_id)`
  - Check the status of a research task
  - Returns: Task status information

- `start_clarification(query)`
  - Analyze query and generate clarifying questions if needed
  - Returns: Dictionary with questions and session ID

- `add_clarification_answers(session_id, answers)`
  - Add answers to clarification questions
  - Returns: Session status information

- `get_enriched_query(session_id)`
  - Generate enriched query from clarification session
  - Returns: Enhanced query string

### ResearchConfig

Configuration class for the research agent.

#### Parameters

- `model`: Model to use (required, must be set in `~/.deep_research`)
- `api_key`: OpenAI API key (optional, can use the `OPENAI_API_KEY` environment variable)
- `base_url`: Custom OpenAI-compatible API endpoint (optional, defaults to the standard OpenAI endpoint)
- `timeout`: Maximum time for research in seconds (default: 1800)
- `poll_interval`: Polling interval in seconds (default: 30)
- `max_retries`: Maximum retry attempts (default: 3)
- `enable_clarification`: Enable clarifying questions (default: False)
- `triage_model`: Model for query analysis (default: `gpt-5-mini`)
- `clarifier_model`: Model for query enrichment (default: `gpt-5-mini`)
- `clarification_api_key`: Custom API key for clarification models (optional, defaults to `api_key`)
- `clarification_base_url`: Custom OpenAI-compatible endpoint for clarification models (optional, defaults to `base_url`)

## Development

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=deep_research_mcp tests/

# Run specific test file
pytest tests/test_agent.py
```
