"""AWS Bedrock client for LLM and embedding generation."""
import boto3
import json
from typing import List, Dict, Any
from app.config import settings
import logging

logger = logging.getLogger(__name__)


class BedrockClient:
    """Client for AWS Bedrock API interactions."""
    
    def __init__(self):
        """Initialize Bedrock runtime client."""
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
    
    def generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding vector for given text using Amazon Titan.
        
        Args:
            text: Text to embed
            
        Returns:
            Embedding vector as list of floats
        """
        try:
            if not text or not text.strip():
                # Return zero vector for empty text to avoid API errors
                # Titan embeddings are 1536 dims
                return [0.0] * 1536

            # Titan embedding request format
            request_body = json.dumps({
                "inputText": text
            })
            
            response = self.client.invoke_model(
                modelId=self.embedding_model_id,
                body=request_body,
                contentType='application/json',
                accept='application/json'
            )
            
            response_body = json.loads(response['body'].read())
            embedding = response_body.get('embedding', [])
            return embedding
            
        except Exception as e:
            logger.error(f"Error generating embedding: {str(e)}")
            raise

    def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a list of texts in parallel.
        
        Args:
            texts: List of strings to embed
            
        Returns:
            List of embedding vectors
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from tqdm import tqdm
        
        if not texts:
            return []

        logger.info(f"Generating embeddings for {len(texts)} chunks in parallel...")
        
        # Parallelize using ThreadPoolExecutor
        # 10-20 threads is usually safe for Bedrock default quotas (50 TPS)
        max_workers = 15
        embeddings = [None] * len(texts)
        
        with tqdm(total=len(texts), desc="✨ Generating Embeddings", unit="chunk") as pbar:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Map original index to future to maintain order
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
                        # Provide a fallback zero vector so the whole batch doesn't fail
                        embeddings[idx] = [0.0] * 1536
                    
                    pbar.update(1)
        
        return embeddings
    
    def generate_simple_text(self, prompt: str) -> str:
        """
        Generate a simple text response without context or grounding.
        Perfect for utility tasks like auto-naming sessions.
        """
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
    ) -> str:
        """
        Generate a response using Claude with strict grounding.
        
        Args:
            user_message: Current user message
            context: Retrieved context from RAG
            conversation_history: Previous messages (last 5)
            use_knowledge_base: Whether knowledge base access is enabled
            
        Returns:
            Generated response text
        """
        try:
            # Build conversation with strict grounding system prompt
            if use_knowledge_base and context:
                system_prompt = """You are IT Query Specialist, an intelligent assistant built by the Perplex Squad team to help analyze IT support tickets and technical documentation.

IDENTITY RULE (HIGHEST PRIORITY):
- When asked "who are you", "what are you", "who created you", "who made you", or any variation, you MUST respond with exactly:
  "I'm IT Query Specialist, built by the Perplex Squad team to help you navigate IT support tickets and technical documentation."
- NEVER mention Anthropic, Claude, OpenAI, Google, Amazon, or any other AI company in your responses.
- You are IT Query Specialist. That is your only identity.

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
7. When the user asks for tickets on a specific TOPIC (e.g., "PDA tickets", "VIA Supervisor tickets"), ONLY include tickets whose summary or description is genuinely about that topic. Skip tickets that are semantically nearby but belong to a different topic area.
8. The context sources are pre-sorted by date when sorting is detected. PRESERVE the order you receive them in. Do not re-sort or shuffle them in your response. State the order you used (ascending/descending) explicitly.
9. When the user asks for "last N" or "top N", list exactly N items maximum.

LIST CONSISTENCY RULES (CRITICAL):
10. When listing items (report names, ticket IDs, etc.), NEVER duplicate the same item. Each entry must be unique.
11. NEVER fabricate, invent, or hallucinate items to reach a number the user requests. Only list items explicitly present in the context.
12. If the context contains N items and the user asks for more, state honestly: "Based on the available data, I found exactly N [items]. Here they are:" and list all N without repetition.
13. Always count final list items before responding and verify no duplicates exist.

GRANULAR CITATION RULE:
14. Every factual claim or list item MUST be followed by a granular citation in the format [S(number)], where 'number' corresponds to the Source index provided in the context (e.g., "[Source S3: ...]" should be cited as [S3]).
15. If multiple sources support a claim, use multiple citations like [S1][S3].
16. Do NOT invent source numbers. Only use numbers present in the provided context markers (e.g., S1, S2, etc.)."""
            else:
                # No context / casual query — respond naturally as the agent persona
                system_prompt = """You are IT Query Specialist, built by the Perplex Squad team.

IDENTITY RULE (HIGHEST PRIORITY):
- When asked "who are you", "what are you", "who created you", "who made you", or any variation, you MUST respond:
  "I'm IT Query Specialist, built by the Perplex Squad team to help you navigate IT support tickets and technical documentation."
- NEVER mention Anthropic, Claude, OpenAI, Google, Amazon, or any other AI company in your responses.

Your role is to help users search through IT support tickets and technical documentation.
For casual conversations and greetings, respond naturally and warmly.
For IT questions without context, let the user know you can help once they ask a specific question.
Never fabricate ticket data or technical facts."""

            if not use_knowledge_base:
                system_prompt = """You are IT Query Specialist, built by the Perplex Squad team. Knowledge base access is currently DISABLED.

IDENTITY RULE (HIGHEST PRIORITY):
- NEVER mention Anthropic, Claude, OpenAI, or any other AI company. You are IT Query Specialist by Perplex Squad.

RULES:
1. For greetings or casual chat, respond naturally and warmly.
2. For IT-specific factual questions, politely state: "Please enable the Knowledge Base toggle to search through tickets and documents."
3. Never make up ticket data or technical facts."""

            # Format messages for Claude with alternating roles strictly enforced
            formatted_messages = []
            
            if conversation_history:
                last_role = None
                for msg in conversation_history:
                    role = msg["role"]
                    content = msg["content"]
                    
                    if not content or not content.strip():
                        continue
                    
                    # Anti-Bias Filter: If assistant said "I don't know", don't include it in history.
                    # This prevents the AI from being biased by its own previous retrieval failures.
                    if role == 'assistant':
                        failure_phrases = [
                            "don't have enough information", 
                            "not in my knowledge base",
                            "enable the knowledge base",
                            "unavailable in the knowledge base"
                        ]
                        if any(phrase in content.lower() for phrase in failure_phrases):
                            logger.info("Filtered failure response from history to avoid grounding bias")
                            continue
                        
                    # Claude requires the first message in the array to be 'user'
                    if not formatted_messages and role == 'assistant':
                        logger.debug("Skipping leading assistant message in history to satisfy Bedrock validation")
                        continue
                        
                    if role == last_role:
                        # Merge content with previous message of same role
                        formatted_messages[-1]["content"] += f"\n\n{content}"
                        continue
                    
                    formatted_messages.append({
                        "role": role,
                        "content": content
                    })
                    last_role = role
            
            # Prepare current user content
            if use_knowledge_base:
                user_content = f"""Here is the retrieved context from the JIRA knowledge base:\n<context>\n{context if context else "None"}\n</context>\n\nPlease answer the following question based ONLY on the context above. Question:\n{user_message}"""
            else:
                user_content = user_message
            
            # Add the current user query as a NEW message, or append if previous was user
            if formatted_messages and formatted_messages[-1]["role"] == "user":
                formatted_messages[-1]["content"] += f"\n\n{user_content}"
            else:
                formatted_messages.append({
                    "role": "user",
                    "content": user_content
                })
            
            # Claude 3 request format
            request_body = json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 4096,
                "temperature": 0.1,  # Low temperature for more factual responses
                "system": system_prompt,
                "messages": formatted_messages
            })

            import time
            gen_start = time.time()
            response = self.client.invoke_model(
                modelId=self.model_id,
                body=request_body,
                contentType='application/json',
                accept='application/json'
            )
            generation_s = round(time.time() - gen_start, 3)

            response_body = json.loads(response['body'].read())

            # Extract text from Claude response
            assistant_message = response_body.get('content', [{}])[0].get('text', '')

            # Extract token counts from Claude's usage block
            usage = response_body.get('usage', {})
            in_tok  = usage.get('input_tokens', 0)
            out_tok = usage.get('output_tokens', 0)
            gen_metrics = {
                "generation_s":  generation_s,
                "input_tokens":  in_tok,
                "output_tokens": out_tok,
                "total_tokens":  in_tok + out_tok,
            }

            return assistant_message, gen_metrics
            
        except Exception as e:
            logger.error(f"Error generating response: {str(e)}")
            raise


# Global Bedrock client instance
bedrock_client = BedrockClient()
