**Smolagents Handbook**

- Purpose: Complete reference for implementing, extending, and operating projects with the smolagents library. Written for AI assistants and developers.
- Scope: Agents, tools, models, prompts, executors, memory/monitoring, CLI, integrations, and security. Includes code you can copy and adapt.

**At A Glance**
- Core modules: `src/smolagents/{agents.py, tools.py, models.py, local_python_executor.py, default_tools.py, remote_executors.py, memory.py, monitoring.py, utils.py}`
- Agent types: `ToolCallingAgent`, `CodeAgent` (multi‑step ReAct with planning, managed agents, streaming)
- Tools: Class‑based tools (`Tool`), function tools (`@tool`), tool collections (Hub, MCP), wrappers (Spaces, Gradio, LangChain)
- Models: Local (Transformers/MLX/vLLM) and API (OpenAI‑compatible, LiteLLM, HF InferenceClient, Azure OpenAI, Amazon Bedrock) with streaming and tool‑calling
- Executors: Local Python sandbox; remote executors (E2B, Docker, Wasm) for code agents
- Defaults: Web search, visit webpage, Python interpreter, Wikipedia, speech‑to‑text, and more
- Prompts: YAML prompt packs for tool‑calling and code agents with planning templates
- CLI: `smolagent` and `webagent` quick start

**Install**
- Minimal: `pip install -e .` or `pip install smolagents`
- Extras: `pip install -e .[openai,litellm,transformers,mlx-lm,bedrock,e2b,gradio,toolkit,all]`


**Concepts**
- Agent: Orchestrates multi‑step reasoning using a model, tools, and optional managed agents.
- Tool: A callable capability with a name, description, input schema, and output type.
- Model: Chat model adapter that produces `ChatMessage` responses; may support streaming and tool‑calling.
- Executor: Sandbox that executes Python produced by `CodeAgent` (local or remote).
- Memory/Monitoring: Structured steps, token usage, logs, and timing.


**Messages & Types**
- `ChatMessage`: `{role: user|assistant|system|tool-call|tool-response, content: str|list, tool_calls?: list, token_usage?: TokenUsage}`
- Tool‑call schema used by OpenAI‑style providers is produced via `get_tool_json_schema(tool)`.
- Streaming deltas (`ChatMessageStreamDelta`) are aggregated via `agglomerate_stream_deltas`.


**Tools**
- Ways to implement tools:
  - Subclass `Tool` and implement `forward(self, ...)`.
  - Use `@tool` decorator on a typed function with a docstring and Args section.
  - Load from Hub (`Tool.from_hub`, `load_tool`), from an MCP server (`ToolCollection.from_mcp`), from Gradio or LangChain wrappers.
- Tool schema keys:
  - `name: str` unique, Python identifier
  - `description: str` concise, actionable
  - `inputs: dict[str, {type: one of string|boolean|integer|number|image|audio|array|object|any|null, description: str, nullable?: bool}]`
  - `output_type: one of AUTHORIZED_TYPES`

Code you can adapt to create a class‑based tool:

```
from smolagents import Tool

class MySum(Tool):
    name = "sum_numbers"
    description = "Adds two numbers."
    inputs = {
        "a": {"type": "number", "description": "First number"},
        "b": {"type": "number", "description": "Second number"},
    }
    output_type = "number"

    def forward(self, a: float, b: float) -> float:
        return a + b
```

Using the `@tool` decorator (infers schema from type hints + docstring):

```
from smolagents import tool

@tool
def search_docs(query: str, max_results: int = 10) -> str:
    """
    Search internal docs.
    Args:
        query: Text to search.
        max_results: Results to return (1-50).
    """
    # ... implement ...
    return "...markdown summary..."
```

Tool utilities and conversions:
- `Tool.to_code_prompt()` and `Tool.to_tool_calling_prompt()` for model prompting context.
- `Tool.validate_arguments()` auto‑checks schema and `forward` signature.
- `validate_tool_arguments(tool, arguments)` to pre‑validate at runtime.
- `launch_gradio_demo(tool)` to get a simple UI for manual runs.
- Save/share tools:
  - `tool.save(path)` writes `tool.py`, `app.py`, `requirements.txt`.
  - `tool.push_to_hub("org/space-name")` publishes a Gradio Space.
  - Load later with `Tool.from_hub(...)` or high‑level `load_tool(repo_id, ...)`.

Wrappers and collections:
- `Tool.from_space(space_id, name, description, api_name=None, token=None)`: calls a Space endpoint.
- `Tool.from_gradio(gradio_tool)` and `Tool.from_langchain(langchain_tool)`.
- `ToolCollection.from_hub(collection_slug, token=None, trust_remote_code=False)` -> loads all Space tools.
- `ToolCollection.from_mcp(server_parameters, trust_remote_code=True)` -> temporarily connects to an MCP server and adapts exposed tools.


**Default Tools**
- `PythonInterpreterTool` (`python_interpreter`): safe Python evaluator with restricted imports. Input: `code: string`. Output: string (stdout + value). Config: `authorized_imports`.
- `FinalAnswerTool` (`final_answer`): terminates an agent run with the final value. Input `answer: any`. Output: any.
- `UserInputTool` (`user_input`): prompts the console for input. Input `question: string`. Output: string.
- `DuckDuckGoSearchTool` (`web_search`): ddgs API search with rate limiting. Input `query: string`. Output: markdown.
- `GoogleSearchTool` (`web_search`): SERP API or Serper. Inputs: `query: string`, `filter_year?: integer`. Output: markdown. Env: `SERPAPI_API_KEY` or `SERPER_API_KEY`.
- `ApiWebSearchTool` (`web_search`): Brave Search (or custom endpoint) via HTTP. Inputs: `query: string`. Output: markdown. Env: `BRAVE_API_KEY`.
- `WebSearchTool` (`web_search`): simple HTML/RSS scrapers for DuckDuckGo or Bing. Inputs: `query: string`. Output: markdown.
- `VisitWebpageTool` (`visit_webpage`): fetches URL and converts HTML to markdown. Input `url: string`. Output: truncated markdown.
- `WikipediaSearchTool` (`wikipedia_search`): summary or full text. Input `query: string`. Output: markdown. Requires `wikipedia-api` and a user agent string.
- `SpeechToTextTool` (`transcriber`): Whisper pipeline. Input `audio`. Output: string. Requires `transformers`.

Note: `TOOL_MAPPING` adds a base set (`python_interpreter`, `web_search`, `visit_webpage`) when `add_base_tools=True` on an agent (with a special case for `ToolCallingAgent`). All tools can be passed explicitly via `tools=[...]`.


**Agents**
- Both agents extend `MultiStepAgent` and implement a ReAct loop with optional planning and managed agents.

Common capabilities
- Planning: initial and iterative re‑planning via YAML prompts. Controlled by `planning_interval`.
- Managed agents: “team members” usable like tools (each with `name`, `description`, `inputs`, `output_type`).
- Final answer validation: pass `final_answer_checks=[callable]` to gate outputs.
- Logging: rich console, images, timings, token usage; streaming supported if model supports `generate_stream`.

`ToolCallingAgent`
- Produces OpenAI‑style tool calls. The model returns `tool_calls` or plain text parsed into a tool call.
- Creates a combined registry of `tools` and `managed_agents` and passes it to the model via `tools` and `tool_choice`.
- Parallel tool execution when multiple tool calls are returned in a single step.

Quick start:

```
from smolagents import ToolCallingAgent, InferenceClientModel, WebSearchTool

agent = ToolCallingAgent(
    tools=[WebSearchTool()],
    model=InferenceClientModel(model_id="Qwen/Qwen2.5-Coder-32B-Instruct"),
    planning_interval=3,
    stream_outputs=True,
)
print(agent.run("What’s new on Hugging Face this week?"))
```

`CodeAgent`
- The model emits Python “action” code blocks instead of JSON tool calls.
- Code executes in a sandboxed Python executor with authorized imports; code can call tools as functions.
- Executors: `local` (default), `e2b`, `docker`, `wasm` via `executor_type` and `executor_kwargs`.
- Structured internal generation optional (`use_structured_outputs_internally=True`) to enforce “thought + code”.
- Custom code block tags: pass `code_block_tags="markdown"` for triple‑backtick fences, or a `(open, close)` tuple.

Quick start:

```
from smolagents import CodeAgent, InferenceClientModel, WebSearchTool

agent = CodeAgent(
    tools=[WebSearchTool()],
    model=InferenceClientModel(),
    additional_authorized_imports=["numpy"],
    executor_type="local",
    max_steps=10,
)
agent.run("Compute the mean of [1, 2, 3], then search for the result and summarize.")
```

Managed agents inside an agent:

```
researcher = ToolCallingAgent(
    tools=[WebSearchTool()],
    model=InferenceClientModel(),
    name="researcher",
    description="Deep‑dive web researcher",
    provide_run_summary=True,
)
manager = CodeAgent(
    tools=[],
    managed_agents=[researcher],
    model=InferenceClientModel(),
)
manager.run("Draft a one‑page brief on Smolagents with citations.")
```


**Local Python Executor**
- File: `local_python_executor.py`. Executes model code safely with restrictions.
- Built‑ins exposed: curated subset (`BASE_PYTHON_TOOLS`), plus math helpers and safe wrappers.
- Security: disallows dangerous modules/functions, dunder attributes, unapproved builtins; validates imports against an allowlist (`authorized_imports`).
- State: persists variables between steps; captures `print` output under `_print_outputs`.
- Final answer flow: the `final_answer()` tool triggers a dedicated exception to terminate execution cleanly.

Authorize imports:

```
agent = CodeAgent(
  tools=[...],
  model=InferenceClientModel(),
  additional_authorized_imports=["pandas", "numpy", "requests"],
)
```

Remote executors (for isolation or portability):
- `E2BExecutor`: runs in an e2b sandbox (pip extra `e2b`).
- `DockerExecutor`: spins a Jupyter Kernel Gateway inside Docker and executes over websockets.
- `WasmExecutor`: runs Python in Pyodide on Deno with strict permissions.


**Models**
- Base class: `Model` with `generate()` and optional `generate_stream()`.
- Common preparation: `_prepare_completion_kwargs()` flattens/merges messages, stop sequences, response formats, and OpenAI‑style tool specs.
- Structured outputs: only certain providers support `response_format` (see `STRUCTURED_GENERATION_PROVIDERS = ["cerebras", "fireworks-ai"]`).
- Stop sequences behavior: `supports_stop_parameter()` disables `stop` for OpenAI `o3`, `o4-mini`, `gpt-5*` families.

Local backends
- `TransformersModel`: loads `AutoModelForCausalLM` or `AutoModelForImageTextToText` with tokenizers/processors. Supports text and VLMs; stop sequences via custom stopping criteria; streaming with `TextIteratorStreamer`.
- `VLLMModel`: uses `vllm.LLM` and its chat template for fast generation. Supports basic `guided_json` for structured outputs.
- `MLXModel`: Apple Silicon via `mlx-lm` stream API with stop handling.

API/hosted backends
- `OpenAIServerModel` (alias `OpenAIModel`): OpenAI‑compatible APIs, including Fireworks, Groq, etc., by changing `api_base`. Supports streaming and tool‑calling.
- `AzureOpenAIServerModel` (alias `AzureOpenAIModel`): Azure OpenAI deployments using `azure_endpoint`/`api_version`.
- `LiteLLMModel`: calls hundreds of providers through LiteLLM; streaming support; optional `LiteLLMRouterModel` for routing/HA.
- `InferenceClientModel`: Hugging Face Inference Providers (serverless endpoints or base_url). Handles providers list, token, bill_to, and optional structured outputs when provider supports it.
- `AmazonBedrockServerModel`: Bedrock runtime client with role mapping and request shaping; stop via inference config; removes non‑Bedrock fields.

Model selection examples:

```
from smolagents import (
  InferenceClientModel, OpenAIServerModel, LiteLLMModel, TransformersModel, VLLMModel
)

# Hugging Face providers
hf = InferenceClientModel(model_id="Qwen/Qwen2.5-Coder-32B-Instruct", provider="nebius")

# OpenAI‑compatible server (e.g., Fireworks)
fw = OpenAIServerModel(api_key="...", api_base="https://api.fireworks.ai/inference/v1", model_id="accounts/.../models/llama")

# LiteLLM to Groq
groq = LiteLLMModel(model_id="groq/llama3-70b-8192", api_key=os.getenv("GROQ_API_KEY"))

# Local Transformers
local = TransformersModel(model_id="Qwen/Qwen2.5-Coder-7B-Instruct", device_map="auto")

# vLLM serverless local
v = VLLMModel(model_id="meta-llama/Llama-3-8B-Instruct")
```

Streaming usage for compatible backends:

```
events = model.generate_stream(messages, tools_to_call_from=tools)
for delta in events:
    if delta.content:
        ...  # partial text
    if delta.tool_calls:
        ...  # partial tool call struct
```


**Prompts**
- Prompt packs live under `src/smolagents/prompts/`:
  - `toolcalling_agent.yaml`: System prompt + planning templates + final answer top‑off.
  - `code_agent.yaml`: Code‑centric ReAct prompting.
  - `structured_code_agent.yaml`: Enforces `{thought, code}` JSON with `response_format` to stabilize output.
- You can pass `instructions` to inject custom guidance, and tweak planning via `planning_interval`.
- `CodeAgent` supports custom code block tags: set `code_block_tags="markdown"` or a custom `(open, close)`.


**Memory & Monitoring**
- Steps (`ActionStep`, `PlanningStep`, `FinalAnswerStep`) accumulate messages, tool calls, outputs, images/audio, timings, and token usage.
- `AgentLogger` renders markdown, panels, images; `Monitor` composes run stats.
- `RunResult` can be returned with `return_full_result=True`.


**Validation & Safety**
- Tool schema and signature validation at tool init; runtime argument validation via `validate_tool_arguments`.
- Python executor enforces:
  - No dunder attribute access nor unsafe builtins.
  - Denylisted modules/functions (e.g., `os.system`, `subprocess`, `__import__`).
  - Import allowlist; partial wildcard support (`pkg.*`) and `"*"` to allow all (use carefully).
- Remote executors isolate code outside the host process (E2B/Docker/Wasm). Prefer these for untrusted workloads.


**CLI**
- `smolagent`: run a `CodeAgent` from terminal.
  - Example: `smolagent --model-type InferenceClientModel --model-id Qwen/Qwen2.5-Coder-32B-Instruct --tools web_search --imports numpy "What is the pi estimate to 6 decimals?"`
  - Flags: `--model-type`, `--model-id`, `--api-base`, `--api-key`, `--provider`, `--tools`, `--imports`, `--verbosity-level`.
- `webagent`: drive a real browser with Helium + CodeAgent (see `vision_web_browser.py`). Requires a vision‑capable model for complex tasks.


**Integration Patterns**
- Use Spaces as tools for composability; publish internal capabilities as Spaces and load via `Tool.from_space`.
- Use MCP servers to surface org systems as tools dynamically (`ToolCollection.from_mcp`).
- Mix models (LiteLLM Router) for resiliency and cost/perf tradeoffs.
- Build gradio demos for each tool to test UX and I/O before agent integration.


**Reference: Essential APIs**
- Tool base and decorator (extracts from `tools.py`):

```
class Tool(BaseTool):
    name: str
    description: str
    inputs: dict[str, dict[str, str | type | bool]]
    output_type: str
    def forward(self, *args, **kwargs): ...

def tool(tool_function: Callable) -> Tool:  # turns a typed function into a Tool
    ...  # infers name/description/inputs/return from docstring/type hints
```

- Agent types (extracts from `agents.py`):

```
class MultiStepAgent:
    def run(self, task: str, images: list[PIL.Image.Image] | None = None, return_full_result: bool | None = None): ...
    def step(self, memory_step: ActionStep) -> Any: ...

class ToolCallingAgent(MultiStepAgent):
    # uses model tool-calling and parallel tool execution
    ...

class CodeAgent(MultiStepAgent):
    def __init__(..., executor_type: Literal["local","e2b","docker","wasm"] = "local", ...): ...
    def create_python_executor(self) -> PythonExecutor: ...
```

- Models (extracts from `models.py`):

```
class Model:
    def generate(self, messages: list[ChatMessage], *, stop_sequences=None, response_format=None, tools_to_call_from=None, **kwargs) -> ChatMessage: ...
    def generate_stream(self, ...) -> Generator[ChatMessageStreamDelta]: ...  # optional

class TransformersModel(Model): ...
class VLLMModel(Model): ...
class MLXModel(Model): ...
class OpenAIServerModel(Model): ...
class AzureOpenAIServerModel(OpenAIServerModel): ...
class LiteLLMModel(Model): ...
class LiteLLMRouterModel(LiteLLMModel): ...
class InferenceClientModel(Model): ...
class AmazonBedrockServerModel(Model): ...
```

- Executors (extracts from `local_python_executor.py` and `remote_executors.py`):

```
class PythonExecutor(ABC):
    def send_tools(self, tools: dict[str, Tool]) -> None: ...
    def send_variables(self, variables: dict[str, Any]) -> None: ...
    def __call__(self, code_action: str) -> CodeOutput: ...

class LocalPythonExecutor(PythonExecutor): ...
class E2BExecutor(PythonExecutor): ...
class DockerExecutor(PythonExecutor): ...
class WasmExecutor(PythonExecutor): ...
```


**Patterns & Tips**
- Keep tool descriptions concrete and short; list arguments and return semantics.
- Prefer returning markdown from tools for readable logs and downstream LLM interpretation.
- Use `planning_interval` to re‑plan on long tasks; stream outputs during planning and acting to tighten feedback loops.
- Validate tool arguments before executing costly actions.
- For CodeAgent, start with `local` executor in trusted contexts; adopt `wasm` or `e2b` for untrusted code.
- For OpenAI‑style servers that do not support `stop`, rely on prompt templates and natural termination markers.
- Use `response_format` for structured internal generation when supported to reduce parsing errors.


**Troubleshooting**
- “No tool call was found”: the model returned plain text without a tool call; use `parse_tool_calls` or adjust prompts.
- “Forbidden function evaluation”: CodeAgent attempted to call disallowed builtins; include it in authorized imports or wrap in a tool.
- “No results found” in search tools: loosen query or adjust year filter.
- Docker executor startup issues: confirm Docker is running and port availability; inspect logs for kernel gateway errors.
- Bedrock: ensure required boto3 version and credentials (or API key) are present.


**CLI Recipes**
- Fireworks via OpenAI client: `smolagent --model-type OpenAIServerModel --api-base https://api.fireworks.ai/inference/v1 --api-key $FIREWORKS_API_KEY --model-id accounts/fireworks/models/llama-v3p1-70b-instruct`.
- LiteLLM Groq: `smolagent --model-type LiteLLMModel --model-id groq/llama-3.1-70b --api-key $GROQ_API_KEY`.
- Local Transformers: `smolagent --model-type TransformersModel --model-id Qwen/Qwen2.5-Coder-7B-Instruct --tools web_search`.


**Security Notes**
- Never hardcode secrets; prefer environment variables (`python-dotenv` supported).
- Review third‑party tool code before loading with `Tool.from_hub` or MCP; pass `trust_remote_code=True` only when appropriate.
- When exposing broad imports (`"*"`), ensure environment packages are present and acceptable for your threat model.


**Repo Development**
- Create env: `python -m venv .venv && source .venv/bin/activate && pip install -e .[dev]`
- Lint: `make quality`; Auto‑fix: `make style`; Tests: `make test`
- CLI quick check: `smolagent --help`, `webagent --help`


**Appendix: Full Default Tools Map**
- Available class names and canonical names:
  - `PythonInterpreterTool` -> `python_interpreter`
  - `FinalAnswerTool` -> `final_answer`
  - `UserInputTool` -> `user_input`
  - `DuckDuckGoSearchTool` -> `web_search`
  - `GoogleSearchTool` -> `web_search`
  - `ApiWebSearchTool` -> `web_search`
  - `WebSearchTool` -> `web_search`
  - `VisitWebpageTool` -> `visit_webpage`
  - `WikipediaSearchTool` -> `wikipedia_search`
  - `SpeechToTextTool` -> `transcriber`

For up‑to‑date signatures and behavior, see `src/smolagents/default_tools.py`.


**Appendix: Prompt Keys**
- `toolcalling_agent.yaml` keys: `system_prompt`, `planning.initial_plan`, `planning.update_plan_pre_messages`, `planning.update_plan_post_messages`, `managed_agent.task`, `managed_agent.report`, `final_answer.pre_messages`, `final_answer.post_messages`.
- `code_agent.yaml` and `structured_code_agent.yaml` follow similar structure tailored for code outputs.


That’s the core of smolagents. With these APIs and patterns, assistants can implement tools, assemble agents, choose backends, and run safely in a variety of environments.

