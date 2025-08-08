# Deep Research MCP

A Python-based agent that integrates OpenAI's Deep Research API with Claude Code through the Model Context Protocol (MCP). This enables Claude Code to perform comprehensive, autonomous research tasks with web search, code execution, and citation management capabilities.

## Features

- 🔍 **Autonomous Research**: Automatically decomposes complex queries into research strategies
- 🌐 **Real-time Web Search**: Built-in web search capabilities for current information
- 💻 **Code Execution**: Integrated code interpreter for data analysis and visualization
- 📚 **Citation Management**: Automatic source attribution with metadata tracking
- 🔄 **Async Operations**: Full asynchronous support for long-running research tasks
- 🛡️ **Rate Limiting**: Built-in rate limiting and retry logic
- 🔌 **MCP Integration**: Seamless integration with Claude Code via Model Context Protocol

## Prerequisites

- Python 3.9+
- OpenAI API key with access to Deep Research models
- Claude Code (for MCP integration)

## Installation

### Quick Install

```bash
# Clone the repository
git clone https://github.com/pminervini/deep-research-mcp.git
cd deep-research-mcp

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY
```

### Development Install

```bash
# Install with development dependencies
pip install -r requirements.txt
pip install -e .

# Or using Poetry
poetry install
```

## Configuration

### Environment Variables

Create a `.env` file in the project root:

```bash
# Required
OPENAI_API_KEY=sk-your-api-key-here

# Optional
RESEARCH_MODEL=o3-deep-research-2025-06-26  # or o4-mini-deep-research-2025-06-26
RESEARCH_TIMEOUT=1800  # Maximum time in seconds (default: 30 minutes)
POLL_INTERVAL=30  # Polling interval in seconds (default: 30)
MAX_RETRIES=3  # Maximum retry attempts (default: 3)
LOG_LEVEL=INFO  # Logging level (DEBUG, INFO, WARNING, ERROR)
```

### Claude Code Integration

1. **Configure MCP Server**

Create or update `~/.config/claude-code/mcp.json`:

```json
{
  "mcpServers": {
    "deep-research": {
      "command": "python",
      "args": ["/path/to/deep-research-mcp/src/deep_research_mcp/mcp_server.py"],
      "env": {
        "OPENAI_API_KEY": "${OPENAI_API_KEY}",
        "RESEARCH_MODEL": "o3-deep-research-2025-06-26"
      }
    }
  }
}
```

2. **Restart Claude Code** to load the MCP server

3. **Use in Claude Code**:
   - The research tools will appear in Claude Code's tool palette
   - Simply ask Claude to "research [your topic]" and it will use the Deep Research agent

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
```

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

### ResearchConfig

Configuration class for the research agent.

#### Parameters

- `api_key`: OpenAI API key (required)
- `model`: Model to use (default: "o3-deep-research-2025-06-26")
- `timeout`: Maximum time for research in seconds (default: 1800)
- `poll_interval`: Polling interval in seconds (default: 30)
- `max_retries`: Maximum retry attempts (default: 3)

## Cost Considerations

Deep Research API pricing (as of January 2025):
- **o3-deep-research-2025-06-26**: $40 per 1M output tokens
- **o4-mini-deep-research-2025-06-26**: Lower cost alternative with faster processing

Monitor your usage carefully as research tasks can generate substantial token usage.

## Error Handling

The agent includes comprehensive error handling:

- **Rate Limiting**: Automatic retry with exponential backoff
- **Timeouts**: Configurable timeout with automatic task cancellation
- **Network Errors**: Retry logic for transient failures
- **API Errors**: Detailed error messages and logging

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
