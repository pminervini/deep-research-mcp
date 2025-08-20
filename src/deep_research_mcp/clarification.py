# -*- coding: utf-8 -*-

"""
Clarification agents for enhancing research queries.
Based on the four-agent pipeline pattern.
"""

import json
import logging
import uuid
from typing import Dict, Any, List, Optional
from openai import OpenAI
import instructor
from pydantic import BaseModel

from deep_research_mcp.config import ResearchConfig
from deep_research_mcp.prompts import PromptManager

logger = logging.getLogger(__name__)


class TriageResponse(BaseModel):
    """Structured response from triage agent"""

    needs_clarification: bool
    reasoning: str
    potential_clarifications: List[str]
    query_assessment: str


class TriageAgent:
    """Analyzes queries to determine if clarification is needed"""

    def __init__(self, config: ResearchConfig, prompt_manager: Optional[PromptManager] = None):
        self.config = config
        self.prompt_manager = prompt_manager or PromptManager()

        # Initialize OpenAI client with custom endpoint if provided
        kwargs = {}
        # Use clarification-specific API key if provided, otherwise fall back to general api_key
        if config.clarification_api_key:
            kwargs["api_key"] = config.clarification_api_key
        elif config.api_key:
            kwargs["api_key"] = config.api_key
        # Use clarification-specific base URL if provided, otherwise fall back to general base_url
        if config.clarification_base_url:
            kwargs["base_url"] = config.clarification_base_url
        elif config.base_url:
            kwargs["base_url"] = config.base_url
        openai_client = OpenAI(**kwargs)
        self.client = instructor.from_openai(openai_client)

    def analyze_query(self, user_query: str) -> Dict[str, Any]:
        """
        Analyze query and decide if clarification is needed

        Returns:
            Dictionary with needs_clarification, reasoning, and potential_clarifications
        """
        logger.info("TriageAgent: Analyzing query for clarification needs")

        triage_prompt = self.prompt_manager.get_triage_prompt(user_query=user_query)

        try:
            response = self.client.chat.completions.create(
                model=self.config.triage_model,
                messages=[{"role": "user", "content": triage_prompt}],
                temperature=0.3,
                response_model=TriageResponse,
            )

            result = response.model_dump()
            logger.info(
                f"Triage assessment: {result.get('query_assessment', 'No assessment')}"
            )
            return result

        except Exception as e:
            logger.error(f"Triage agent error: {e}")
            return {
                "needs_clarification": False,
                "reasoning": f"Triage agent error: {str(e)}",
                "potential_clarifications": [],
                "query_assessment": "Error during assessment",
            }


class ClarifierAgent:
    """Enriches queries based on user responses to clarifying questions"""

    def __init__(self, config: ResearchConfig, prompt_manager: Optional[PromptManager] = None):
        self.config = config
        self.prompt_manager = prompt_manager or PromptManager()

        # Initialize OpenAI client with custom endpoint if provided
        openai_kwargs = {}
        # Use clarification-specific API key if provided, otherwise fall back to general api_key
        if config.clarification_api_key:
            openai_kwargs["api_key"] = config.clarification_api_key
        elif config.api_key:
            openai_kwargs["api_key"] = config.api_key
        # Use clarification-specific base URL if provided, otherwise fall back to general base_url
        if config.clarification_base_url:
            openai_kwargs["base_url"] = config.clarification_base_url
        elif config.base_url:
            openai_kwargs["base_url"] = config.base_url
        openai_client = OpenAI(**openai_kwargs)
        self.client = instructor.from_openai(openai_client)

    def enrich_query(self, user_query: str, qa_pairs: List[Dict[str, str]]) -> str:
        """
        Create enriched query based on original query and Q&A pairs

        Args:
            user_query: Original research query
            qa_pairs: List of dicts with 'question' and 'answer' keys

        Returns:
            Enriched, more specific research query
        """
        logger.info("ClarifierAgent: Enriching query with user context")

        # Format the Q&A context
        enriched_context = []
        for qa in qa_pairs:
            if qa.get("answer") and qa["answer"].strip():
                enriched_context.append(f"Q: {qa['question']}\nA: {qa['answer']}")
            else:
                enriched_context.append(
                    f"Q: {qa['question']}\nA: [No specific preference provided]"
                )

        enrichment_prompt = self.prompt_manager.get_enrichment_prompt(
            user_query=user_query, 
            enriched_context=chr(10).join(enriched_context)
        )

        try:
            response = self.client.chat.completions.create(
                model=self.config.clarifier_model,
                messages=[{"role": "user", "content": enrichment_prompt}],
                temperature=0.2,
            )

            enriched_query = response.choices[0].message.content.strip()
            logger.info(f"Query enriched successfully")
            return enriched_query

        except Exception as e:
            logger.error(f"ClarifierAgent error: {e}")
            # Fallback to original query if enrichment fails
            return user_query


class ClarificationSession:
    """Manages a clarification session with unique ID and state"""

    def __init__(self, session_id: str, original_query: str, questions: List[str]):
        self.session_id = session_id
        self.original_query = original_query
        self.questions = questions
        self.answers: List[str] = []
        self.created_at = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert session to dictionary for serialization"""
        return {
            "session_id": self.session_id,
            "original_query": self.original_query,
            "questions": self.questions,
            "answers": self.answers,
            "total_questions": len(self.questions),
            "answered_questions": len(self.answers),
            "is_complete": len(self.answers) >= len(self.questions),
        }


class ClarificationManager:
    """Manages the complete clarification pipeline"""

    def __init__(self, config: ResearchConfig, prompt_manager: Optional[PromptManager] = None):
        self.config = config
        self.prompt_manager = prompt_manager or PromptManager()
        self.triage_agent = TriageAgent(config, self.prompt_manager)
        self.clarifier_agent = ClarifierAgent(config, self.prompt_manager)
        self._sessions: Dict[str, ClarificationSession] = {}

    def start_clarification(self, user_query: str) -> Dict[str, Any]:
        """
        Start clarification process for a query

        Returns:
            Dictionary with clarification status and questions
        """
        if not self.config.enable_clarification:
            return {
                "needs_clarification": False,
                "reasoning": "Clarification is disabled in configuration",
            }

        # Analyze query with triage agent
        triage_result = self.triage_agent.analyze_query(user_query)

        if not triage_result.get("needs_clarification", False):
            return triage_result

        # Create clarification session
        session_id = str(uuid.uuid4())
        questions = triage_result.get("potential_clarifications", [])

        session = ClarificationSession(session_id, user_query, questions)
        self._sessions[session_id] = session

        result = triage_result.copy()
        result["session_id"] = session_id
        result["questions"] = questions
        result["total_questions"] = len(questions)

        return result

    def add_answers(self, session_id: str, answers: List[str]) -> Dict[str, Any]:
        """
        Add answers to a clarification session

        Args:
            session_id: Session identifier
            answers: List of answers to the clarification questions

        Returns:
            Dictionary with session status
        """
        if session_id not in self._sessions:
            return {"error": f"Session {session_id} not found"}

        session = self._sessions[session_id]
        session.answers = answers

        return {
            "session_id": session_id,
            "status": "answers_recorded",
            "total_questions": len(session.questions),
            "answered_questions": len(session.answers),
            "is_complete": len(session.answers) >= len(session.questions),
        }

    def get_enriched_query(self, session_id: str) -> Optional[str]:
        """
        Get enriched query for a completed clarification session

        Args:
            session_id: Session identifier

        Returns:
            Enriched query string or None if session not found/incomplete
        """
        if session_id not in self._sessions:
            return None

        session = self._sessions[session_id]

        # Create Q&A pairs for enrichment
        qa_pairs = []
        for i, question in enumerate(session.questions):
            answer = session.answers[i] if i < len(session.answers) else ""
            qa_pairs.append({"question": question, "answer": answer})

        # Generate enriched query
        enriched_query = self.clarifier_agent.enrich_query(
            session.original_query, qa_pairs
        )

        # Clean up session (optional - could keep for debugging)
        # del self._sessions[session_id]

        return enriched_query

    def get_session(self, session_id: str) -> Optional[ClarificationSession]:
        """Get session by ID"""
        return self._sessions.get(session_id)
