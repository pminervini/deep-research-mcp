# -*- coding: utf-8 -*-

"""
Deep Research Agent implementation for OpenAI's Deep Research API.
"""

import asyncio
import time
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import logging
from openai import OpenAI
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from deep_research_mcp.config import ResearchConfig
from deep_research_mcp.errors import ResearchError, RateLimitError, TaskTimeoutError

logger = logging.getLogger(__name__)


class DeepResearchAgent:
    """Deep Research agent with full async support"""

    def __init__(self, config: ResearchConfig):
        self.config = config
        self.client = OpenAI(api_key=config.api_key)
        self.logger = logging.getLogger(__name__)

    async def research(
        self,
        query: str,
        system_prompt: Optional[str] = None,
        include_code_interpreter: bool = True,
        callback_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Perform deep research on a query with full async handling

        Args:
            query: Research question or topic
            system_prompt: Optional system instructions for research approach
            include_code_interpreter: Whether to enable code execution
            callback_url: Optional webhook URL for completion notification

        Returns:
            Dictionary with final report, citations, and metadata
        """

        # Prepare input messages
        input_messages = []
        if system_prompt:
            input_messages.append(
                {
                    "role": "developer",
                    "content": [{"type": "input_text", "text": system_prompt}],
                }
            )

        input_messages.append(
            {"role": "user", "content": [{"type": "input_text", "text": query}]}
        )

        # Configure tools
        tools = [{"type": "web_search_preview"}]
        if include_code_interpreter:
            tools.append(
                {
                    "type": "code_interpreter",
                    "container": {"type": "auto", "file_ids": []},
                }
            )

        # Start background research task
        response = await self._create_research_task(input_messages, tools)

        # Poll for completion with timeout
        try:
            final_response = await self._wait_for_completion(response.id)
        except ResearchError as e:
            # Return error details instead of raising
            return {"status": "failed", "message": str(e)}

        # Send callback if provided
        if callback_url and final_response.get("status") == "completed":
            await self._send_completion_callback(callback_url, final_response)

        return self._extract_results(final_response)

    @retry(
        stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10)
    )
    async def _create_research_task(
        self, input_messages: List[Dict], tools: List[Dict]
    ):
        """Create research task with retry logic"""
        try:
            response = self.client.responses.create(
                model=self.config.model,
                input=input_messages,
                tools=tools,
                reasoning={"summary": "auto"},
                background=True,  # Essential for long-running tasks
            )
            self.logger.info(f"Research task started: {response.id}")
            return response
        except Exception as e:
            self.logger.error(f"Failed to create research task: {e}")
            raise

    async def _wait_for_completion(self, task_id: str) -> Dict[str, Any]:
        """Poll for task completion with timeout"""
        start_time = time.time()

        while time.time() - start_time < self.config.timeout:
            try:
                response = self.client.responses.retrieve(task_id)

                if response.status == "completed":
                    self.logger.info(f"Research completed: {task_id}")
                    return response
                elif response.status == "failed":
                    error_details = getattr(response, "error", None)
                    if error_details:
                        # Handle different error object types
                        if hasattr(error_details, "get"):
                            error_msg = f"Research task failed: {error_details.get('message', 'Unknown error')}"
                            if error_details.get("code"):
                                error_msg += f" (Code: {error_details['code']})"
                        else:
                            error_msg = f"Research task failed: {str(error_details)}"
                    else:
                        error_msg = f"Research task failed: {task_id}"
                    raise ResearchError(error_msg)

                # Continue polling
                self.logger.debug(f"Task {task_id} status: {response.status}")
                await asyncio.sleep(self.config.poll_interval)

            except Exception as e:
                self.logger.error(f"Error polling task {task_id}: {e}")
                await asyncio.sleep(5)  # Brief backoff on error

        # Timeout reached, attempt cancellation
        self.logger.warning(f"Task {task_id} timed out, attempting cancellation")
        try:
            self.client.responses.cancel(task_id)
        except:
            pass

        raise TaskTimeoutError(
            f"Research task {task_id} did not complete within {self.config.timeout} seconds"
        )

    async def _send_completion_callback(
        self, callback_url: str, response_data: Dict[str, Any]
    ):
        """Send completion notification to callback URL"""
        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    callback_url,
                    json={
                        "status": "completed",
                        "task_id": response_data.get("id"),
                        "timestamp": time.time(),
                        "result_preview": response_data.get("output", [])[-1]
                        .get("content", [{}])[0]
                        .get("text", "")[:500],
                    },
                    timeout=30,
                )
        except Exception as e:
            self.logger.error(f"Failed to send callback to {callback_url}: {e}")

    def _extract_results(self, response) -> Dict[str, Any]:
        """Extract and structure final results"""
        # Handle failed responses
        if response.status == "failed":
            error_details = getattr(response, "error", None)
            if error_details:
                # Handle different error object types
                if hasattr(error_details, "get"):
                    return {
                        "status": "failed",
                        "message": error_details.get("message", "Unknown error"),
                        "error_code": error_details.get("code"),
                        "task_id": response.id,
                    }
                else:
                    return {
                        "status": "failed",
                        "message": str(error_details),
                        "task_id": response.id,
                    }
            else:
                return {"status": "failed", "message": f"Task failed: {response.id}"}

        if not response.output:
            return {"status": "error", "message": "No output received"}

        # Get final report (last output item)
        final_output = response.output[-1]
        final_report = final_output.content[0].text if final_output.content else ""

        # Extract citations
        citations = []
        if final_output.content and final_output.content[0].annotations:
            for i, annotation in enumerate(final_output.content[0].annotations):
                citations.append(
                    {
                        "index": i + 1,
                        "title": annotation.title,
                        "url": annotation.url,
                        "start_char": annotation.start_index,
                        "end_char": annotation.end_index,
                    }
                )

        # Extract intermediate steps for debugging
        reasoning_steps = [
            item.summary
            for item in response.output
            if item.type == "reasoning" and hasattr(item, "summary")
        ]

        search_queries = [
            item.action.get("query", "")
            for item in response.output
            if item.type == "web_search_call" and hasattr(item, "action")
        ]

        return {
            "status": "completed",
            "final_report": final_report,
            "citations": citations,
            "reasoning_steps": len(reasoning_steps),
            "search_queries": search_queries,
            "total_steps": len(response.output),
            "task_id": response.id,
        }

    async def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """Check the status of a research task"""
        try:
            response = self.client.responses.retrieve(task_id)
            return {
                "task_id": task_id,
                "status": response.status,
                "created_at": getattr(response, "created_at", None),
                "completed_at": getattr(response, "completed_at", None),
            }
        except Exception as e:
            self.logger.error(f"Error checking status for task {task_id}: {e}")
            return {"task_id": task_id, "status": "error", "error": str(e)}
