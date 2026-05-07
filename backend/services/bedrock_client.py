"""AWS Bedrock client for LLM and embedding generation."""
import json
import time
import logging
from typing import Dict, List, Tuple

import boto3

from app.config import settings

logger = logging.getLogger(__name__)

# ── System Prompts ────────────────────────────────────────────────────────────

_IDENTITY_BLOCK = """IDENTITY RULE (HIGHEST PRIORITY):
- When asked "who are you", "what are you", "who created you", "who made you", or any variation, you MUST respond with exactly:
  "I'm IT Query Specialist, built by the Perplex Squad team to help you navigate IT support tickets and technical documentation."
- NEVER mention Anthropic, Claude, OpenAI, Google, Amazon, or any other AI company in your responses.
- You are IT Query Specialist. That is your only identity."""

_FORMATTING_BLOCK = """READABILITY & FORMATTING RULES (CRITICAL):
- Structure your output for MAXIMUM scannability using Markdown.
- Use headings (## or ###) to organize different sections of your answer.
- Use bullet points or numbered lists for all processes and technical details.
- Highlight important terms using **bold text**.
- Keep paragraphs extremely short (1-3 lines max).
- Use tables when comparing tickets, dates, or statuses.
- Add small, professional emojis to improve navigation.
- Separate all sections with blank lines.
- PRIORITIZE structured formatting over large paragraphs. Be clear and readable over verbose."""

_GROUNDED_SYSTEM_PROMPT = f"""You are IT Query Specialist, an intelligent assistant built by the Perplex Squad team to help analyze IT support tickets and technical documentation.

{_IDENTITY_BLOCK}

STRICT GROUNDING RULES:
1. Answer ONLY using information from the "Context from knowledge base". Do NOT use your pre-trained knowledge for technical facts.
2. PAY ATTENTION TO DATES AND TIMES. If the user asks for "recent" issues, look at Creation Dates in the context and state them explicitly.
3. PRIORITIZE the current context over previous turns in the conversation.

RESOLUTION SYNTHESIS RULES (IMPORTANT):
4. If asked how a ticket was resolved/fixed, look for the answer in THIS ORDER:
   a) The "resolution_details" field (most authoritative)
   b) The "resolution" field (e.g., "Fixed", "Done", "Won't Fix")
   c) The COMMENTS thread — look for phrases like "confirmed fixed", "issue resolved", "working now", "Teams", "phone call", "rebooted", "restarted", "script run". Summarize what the comments say.
   d) If the ticket status is "Done" / "Closed" / "Resolved" but comments are vague, state: "The ticket was marked as [status]. Based on the comments, [summarize any relevant activity, even informal ones like confirmation over Teams/email]."
5. Never say "I don't have information" if the ticket IS in the context — even informal resolutions (e.g., "user confirmed fixed over Teams") should be reported as the resolution.
6. If a specific ticket ID (like HCLSM-12345) is mentioned, focus your answer on THAT ticket's data even if other tickets are also shown.

FILTERING AND ORDERING RULES:
7. When the user asks for tickets on a specific TOPIC (e.g., "PDA tickets", "VIA Supervisor tickets"), ONLY include tickets whose summary or description is genuinely about that topic.
8. The context sources are pre-sorted by date when sorting is detected. PRESERVE the order you receive them in.
9. When the user asks for "last N" or "top N", list exactly N items maximum.

LIST CONSISTENCY RULES (CRITICAL):
10. When listing items, NEVER duplicate the same item. Each entry must be unique.
11. NEVER fabricate, invent, or hallucinate items to reach a number the user requests.
12. If the context contains N items and the user asks for more, state honestly: "Based on the available data, I found exactly N [items]."
13. Always count final list items before responding and verify no duplicates exist.

GRANULAR CITATION RULE (ANTI-COLLISION):
14. Every factual claim MUST be followed by a granular citation in the format [S(number)].
15. CRITICAL: Never use Ticket ID numbers as a citation index. The citation [S1745] is ALWAYS WRONG if you only have 60 sources.
16. If multiple sources support a claim, use multiple citations like [S1][S3]. Do NOT invent source numbers.

{_FORMATTING_BLOCK}"""

_CASUAL_SYSTEM_PROMPT = f"""You are IT Query Specialist, built by the Perplex Squad team.

{_IDENTITY_BLOCK}

Your role is to help users search through IT support tickets and technical documentation.
For casual conversations and greetings, respond naturally and warmly.
For IT questions without context, let the user know you can help once they ask a specific question.
Never fabricate ticket data or technical facts.

{_FORMATTING_BLOCK}"""

_KB_DISABLED_SYSTEM_PROMPT = f"""You are IT Query Specialist, built by the Perplex Squad team. Knowledge base access is currently DISABLED.

{_IDENTITY_BLOCK}

RULES:
1. For greetings or casual chat, respond naturally and warmly.
2. For IT-specific factual questions, politely state: "Please enable the Knowledge Base toggle to search through tickets and documents."
3. Never make up ticket data or technical facts.

{_FORMATTING_BLOCK}"""

# Phrases indicating a previous retrieval failure — filter from history to avoid grounding bias
_FAILURE_PHRASES = [
    "don't have enough information",
    "not in my knowledge base",
    "enable the knowledge base",
    "unavailable in the knowledge base"
]


class BedrockClient:
    """Client for AWS Bedrock API interactions."""

    def __init__(self):
        """Initialize Bedrock runtime client."""
        self._build_client()

    def _build_client(self) -> None:
        """Build the boto3 client from current settings. Idempotent."""
        client_kwargs = {
            'service_name': 'bedrock-runtime',
            'region_name': settings.aws_region
        }
        if settings.aws_access_key_id:
            client_kwargs['aws_access_key_id'] = settings.aws_access_key_id
            client_kwargs['aws_secret_access_key'] = settings.aws_secret_access_key
            if settings.aws_session_token:
                client_kwargs['aws_session_token'] = settings.aws_session_token

        self.client = boto3.client(**client_kwargs)
        self.model_id = settings.aws_bedrock_model_id
        self.embedding_model_id = settings.aws_bedrock_embedding_model_id
        logger.info(f"Initialized Bedrock client with model: {self.model_id}")

    def refresh(self) -> None:
        """Reload settings from .env and rebuild the boto3 client.

        Why: AWS SSO session tokens in .env expire every few hours. Rebuilding
        in-process avoids a full server restart when ops rotates credentials.
        """
        from app.config import Settings
        reloaded = Settings()
        # Mutate the shared settings object in place so other modules see new values
        for field in reloaded.model_fields:
            setattr(settings, field, getattr(reloaded, field))
        self._build_client()
        logger.info("BedrockClient credentials refreshed from environment")

    def generate_embedding(self, text: str) -> List[float]:
        """Generate embedding vector for given text using Amazon Titan."""
        try:
            if not text or not text.strip():
                return [0.0] * settings.embedding_dimensions

            request_body = json.dumps({"inputText": text})

            response = self.client.invoke_model(
                modelId=self.embedding_model_id,
                body=request_body,
                contentType='application/json',
                accept='application/json'
            )

            response_body = json.loads(response['body'].read())
            return response_body.get('embedding', [])

        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            raise

    def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a list of texts in parallel."""
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from tqdm import tqdm

        if not texts:
            return []

        logger.info(f"Generating embeddings for {len(texts)} chunks in parallel...")

        embeddings = [None] * len(texts)

        with tqdm(total=len(texts), desc="Generating Embeddings", unit="chunk") as pbar:
            with ThreadPoolExecutor(max_workers=settings.embedding_max_workers) as executor:
                future_to_idx = {
                    executor.submit(self.generate_embedding, text): i
                    for i, text in enumerate(texts)
                }

                for future in as_completed(future_to_idx):
                    idx = future_to_idx[future]
                    try:
                        embeddings[idx] = future.result()
                    except Exception as e:
                        logger.error(f"Failed to generate embedding for chunk {idx}: {e}")
                        embeddings[idx] = [0.0] * settings.embedding_dimensions

                    pbar.update(1)

        return embeddings

    def generate_simple_text(self, prompt: str) -> str:
        """Generate a simple text response without context or grounding."""
        try:
            request_body = json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 100,
                "temperature": 0.5,
                "messages": [{"role": "user", "content": prompt}]
            })

            response = self.client.invoke_model(
                modelId=self.model_id,
                body=request_body,
                contentType='application/json',
                accept='application/json'
            )

            response_body = json.loads(response['body'].read())
            return response_body.get('content', [{}])[0].get('text', '').strip()
        except Exception as e:
            logger.error(f"Error in simple text generation: {e}")
            return ""

    def generate_response(
        self,
        user_message: str,
        context: str,
        conversation_history: List[Dict[str, str]] = None,
        use_knowledge_base: bool = True
    ) -> Tuple[str, Dict]:
        """Generate a response using Claude with strict grounding."""
        try:
            system_prompt = self._select_system_prompt(context, use_knowledge_base)
            formatted_messages = self._format_conversation(conversation_history)
            self._append_user_message(formatted_messages, user_message, context, use_knowledge_base)

            request_body = json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": settings.llm_max_tokens,
                "temperature": settings.llm_temperature,
                "system": system_prompt,
                "messages": formatted_messages
            })

            gen_start = time.time()
            response = self.client.invoke_model(
                modelId=self.model_id,
                body=request_body,
                contentType='application/json',
                accept='application/json'
            )
            generation_s = round(time.time() - gen_start, 3)

            response_body = json.loads(response['body'].read())
            assistant_message = response_body.get('content', [{}])[0].get('text', '')

            usage = response_body.get('usage', {})
            in_tok = usage.get('input_tokens', 0)
            out_tok = usage.get('output_tokens', 0)

            gen_metrics = {
                "generation_s":  generation_s,
                "input_tokens":  in_tok,
                "output_tokens": out_tok,
                "total_tokens":  in_tok + out_tok,
            }

            return assistant_message, gen_metrics

        except Exception as e:
            logger.error(f"Error generating response: {e}")
            raise

    @staticmethod
    def _select_system_prompt(context: str, use_knowledge_base: bool) -> str:
        """Select the appropriate system prompt based on context and KB toggle."""
        if not use_knowledge_base:
            return _KB_DISABLED_SYSTEM_PROMPT
        if context:
            return _GROUNDED_SYSTEM_PROMPT
        return _CASUAL_SYSTEM_PROMPT

    @staticmethod
    def _format_conversation(conversation_history: List[Dict[str, str]] | None) -> List[Dict[str, str]]:
        """Format conversation history for Claude, enforcing alternating roles."""
        formatted_messages = []
        if not conversation_history:
            return formatted_messages

        last_role = None
        for msg in conversation_history:
            role = msg["role"]
            content = msg["content"]

            if not content or not content.strip():
                continue

            # Filter out previous retrieval-failure responses to avoid grounding bias
            if role == 'assistant' and any(phrase in content.lower() for phrase in _FAILURE_PHRASES):
                logger.info("Filtered failure response from history to avoid grounding bias")
                continue

            # Claude requires first message to be 'user'
            if not formatted_messages and role == 'assistant':
                continue

            # Merge consecutive same-role messages
            if role == last_role:
                formatted_messages[-1]["content"] += f"\n\n{content}"
                continue

            formatted_messages.append({"role": role, "content": content})
            last_role = role

        return formatted_messages

    @staticmethod
    def _append_user_message(
        formatted_messages: List[Dict],
        user_message: str,
        context: str,
        use_knowledge_base: bool
    ) -> None:
        """Append the current user query, wrapping with context if KB is enabled."""
        if use_knowledge_base:
            user_content = (
                f"Here is the retrieved context from the JIRA knowledge base:\n"
                f"<context>\n{context or 'None'}\n</context>\n\n"
                f"Please answer the following question based ONLY on the context above. Question:\n{user_message}"
            )
        else:
            user_content = user_message

        if formatted_messages and formatted_messages[-1]["role"] == "user":
            formatted_messages[-1]["content"] += f"\n\n{user_content}"
        else:
            formatted_messages.append({"role": "user", "content": user_content})


# Global Bedrock client instance
bedrock_client = BedrockClient()
