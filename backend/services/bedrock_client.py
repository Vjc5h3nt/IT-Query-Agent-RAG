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
        self.client = boto3.client(
            service_name='bedrock-runtime',
            region_name=settings.aws_region
        )
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
            if use_knowledge_base:
                system_prompt = """You are a helpful, professional assistant that uses a knowledge base to answer questions.

GROUNDING RULES:
1. For factual questions, use ONLY the provided "Context from knowledge base".
2. PRIORITIZE the current "Context from knowledge base" even if it contradicts your previous answers in the conversation history. The knowledge base context can change or be updated between turns.
3. If the answer is in the current context, provide it fully, even if you previously said it wasn't available. Address EVERY part of a multi-point question.
4. If the answer for a specific part is missing, answer the other parts and state clearly which part is unavailable in the knowledge base.
5. If the entire answer is missing, say: "I don't have enough information in my knowledge base to answer that question."
6. DO NOT hallucinate. Be direct and concise.
7. For casual chat or greetings, ignore the knowledge base and answer naturally. """
            else:
                system_prompt = """You are a helpful assistant. Knowledge base access is currently DISABLED.

RULES:
1. For greetings or casual chat, answer naturally.
2. For factual questions, politely state: "Please enable the Knowledge Base in the UI to ask questions about the documents."
3. DO NOT use internal knowledge for factual questions when access is disabled."""

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
                user_content = f"""Context from knowledge base:
{context if context else "None"}

User question: {user_message}"""
            else:
                user_content = user_message
            
            # Check if we should append or merge with last history message
            if formatted_messages and formatted_messages[-1]["role"] == "user":
                formatted_messages[-1]["content"] += f"\n\n--- Next Question ---\n{user_content}"
            else:
                formatted_messages.append({
                    "role": "user",
                    "content": user_content
                })
            
            # Claude 3 request format
            request_body = json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 2000,
                "temperature": 0.1,  # Low temperature for more factual responses
                "system": system_prompt,
                "messages": formatted_messages
            })
            
            response = self.client.invoke_model(
                modelId=self.model_id,
                body=request_body,
                contentType='application/json',
                accept='application/json'
            )
            
            response_body = json.loads(response['body'].read())
            
            # Extract text from Claude response
            assistant_message = response_body.get('content', [{}])[0].get('text', '')
            
            return assistant_message
            
        except Exception as e:
            logger.error(f"Error generating response: {str(e)}")
            raise


# Global Bedrock client instance
bedrock_client = BedrockClient()
