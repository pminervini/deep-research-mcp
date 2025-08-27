# Deep Research MCP

A Python-based agent that integrates research providers with Claude Code through the Model Context Protocol (MCP). It supports both OpenAI (Responses API with web search and code interpreter) and the open-source Open Deep Research stack (based on smolagents).

## Prerequisites

- Python 3.9+
- One of:
  - OpenAI API access (Responses API models, e.g., `o4-mini-deep-research-2025-06-26`)
  - Open Deep Research dependencies (installed via `requirements.txt`)
- Claude Code, or any other assistant supporting MCP integration

## Configuration

### Configuration File

Create a `~/.deep_research` file in your home directory using TOML format.

Common settings:

```toml
[research]                                  # Core Deep Research functionality
provider = "openai"                         # Available options: "openai", "open-deep-research" -- defaults to "openai"
model = "o4-mini-deep-research-2025-06-26"  # OpenAI: model identifier; ODR: LiteLLM model identifier, e.g., openai/qwen/qwen3-coder-30b
api_key = "sk-your-api-key"                 # API key, optional
base_url = "https://api.openai.com/v1"      # OpenAI: OpenAI-compatible endpoint; ODR: LiteLLM-compatible endpoint, e.g., http://localhost:1234/v1

# Task behavior
timeout = 1800
poll_interval = 30
max_retries = 3

# Largely based on https://cookbook.openai.com/examples/deep_research_api/introduction_to_deep_research_api_agents
[clarification]                                       # Optional query clarification component
enable_clarification = false
triage_model = "gpt-5-mini"
clarifier_model = "gpt-5-mini"
instruction_builder_model = "gpt-5-mini"
clarification_api_key = "sk-your-api-key"             # Optional, overrides api_key
clarification_base_url = "https://api.openai.com/v1"  # Optional, overrides base_url

[logging]
level = "INFO"
```

OpenAI provider example:

```toml
[research]
provider = "openai"
model = "o4-mini-deep-research-2025-06-26"  # OpenAI model
api_key = "sk-..."                          # Defaults to OPENAI_API_KEY
base_url = "https://api.openai.com/v1"      # OpenAI-compatible endpoint
timeout = 1800
poll_interval = 30
max_retries = 3
```

Open Deep Research provider example:

```toml
[research]
provider = "open-deep-research"
model = "openai/qwen/qwen3-coder-30b"  # LiteLLM-compatible model id
base_url = "http://localhost:1234/v1"  # LiteLLM-compatible endpoint (local or remote)
api_key = ""                           # Optional if endpoint requires it
timeout = 1800
```

Optional env variables for Open Deep Research tools:

- `SERPAPI_API_KEY` or `SERPER_API_KEY`: enable Google-style search
- `HF_TOKEN`: optional, logs into Hugging Face Hub for gated models

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
    print(f"Research steps: {result['reasoning_steps']}")

# Run the research
asyncio.run(main())
```

### As an MCP Server

The server supports both stdio (default) and HTTP transports:

#### Stdio Transport (Default)
```bash
# Start the MCP server with stdio transport (default)
python src/deep_research_mcp/mcp_server.py

# Or explicitly specify stdio transport  
python src/deep_research_mcp/mcp_server.py --transport stdio
```

#### HTTP Transport
```bash
# Start the MCP server with HTTP transport on default port 8080
python src/deep_research_mcp/mcp_server.py --transport http

# Specify custom host and port for remote access
python src/deep_research_mcp/mcp_server.py --transport http --host 0.0.0.0 --port 3000

# For development with custom settings
python src/deep_research_mcp/mcp_server.py --transport http --host localhost --port 8080
```

### HTTP Transport Use Cases

HTTP transport enables several advanced deployment scenarios:

- **Remote deployment**: Deploy on cloud servers and access from multiple clients
- **Load balancing**: Use HTTP load balancers for high availability
- **Network isolation**: Deploy in DMZ or private networks with HTTP routing
- **Containerization**: Deploy in Docker/Kubernetes with standard HTTP service patterns
- **Development teams**: Share a single research server instance across team members

### Docker Deployment Example

Create a `Dockerfile` for HTTP deployment:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY src/ ./src/

EXPOSE 8080

CMD ["python", "src/deep_research_mcp/mcp_server.py", "--transport", "http", "--host", "0.0.0.0", "--port", "8080"]
```

Build and run:

```bash
# Build the image
docker build -t deep-research-mcp .

# Run with environment variables
docker run -p 8080:8080 -e OPENAI_API_KEY=your-key-here deep-research-mcp

# Or run with config file mounted
docker run -p 8080:8080 -v ~/.deep_research:/root/.deep_research deep-research-mcp
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
[clarification]
enable_clarification = true
triage_model = "gpt-5-mini"                                    # Optional, defaults to gpt-5-mini
clarifier_model = "gpt-5-mini"                                 # Optional, defaults to gpt-5-mini
instruction_builder_model = "gpt-5-mini"                       # Optional, defaults to gpt-5-mini
clarification_api_key = "sk-your-clarification-api-key-here"   # Optional custom API key for clarification models
clarification_base_url = "https://custom-api.example.com/v1"   # Optional custom endpoint for clarification models
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

### Integration with AI Assistants

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

- `provider`: Research provider (`openai` or `open-deep-research`; default: `openai`)
- `model`: Model identifier
  - OpenAI: Responses model (e.g., `gpt-5-mini`)
  - Open Deep Research: LiteLLM model id (e.g., `openai/qwen/qwen3-coder-30b`)
- `api_key`: API key for the configured endpoint (optional). Defaults to env `OPENAI_API_KEY`.
- `base_url`: OpenAI-compatible API base URL (optional). Defaults to env `OPENAI_BASE_URL`.
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
pytest --cov=deep-research-mcp tests/

# Run specific test file
pytest tests/test_agent.py
```
